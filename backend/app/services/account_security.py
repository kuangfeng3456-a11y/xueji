"""账号安全：多设备会话与无邮件/短信通道下的自助找回。

设计取舍：
- 会话：JWT 里带 jti，服务端存一行会话记录。撤销即失效，「退出其他设备」
  和「改密后其它设备掉线」才有真实效果，而不是只删前端的 localStorage。
- 找回：没有邮件与短信，因此只做两种可自证的凭据 —— 密保问题（2 个）
  与一次性恢复码。两者都是「只有本人知道」的知识因子，都不依赖外部通道。
- 答案与恢复码一律归一化后哈希存储：用户忘记大小写、多打空格也能通过，
  而泄露数据库也拿不到原始答案。
"""

import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuthSession, User
from ..security import hash_password, new_jti, verify_password

# 密保问题题库：固定选项而非自由输入，避免「问题本身就是答案提示」，
# 也避免用户写出别人能搜到的公开信息（如「我的学校」）。
QUESTIONS: list[dict] = [
    {"key": "primary_school", "text": "你就读的小学叫什么名字？"},
    {"key": "first_teacher", "text": "你印象最深的老师姓什么？"},
    {"key": "birth_city", "text": "你出生在哪个城市？"},
    {"key": "childhood_pet", "text": "你童年养过的第一只宠物叫什么？"},
    {"key": "old_friend", "text": "你小学时最好的朋友叫什么？"},
    {"key": "favorite_book", "text": "对你影响最大的一本书是什么？"},
    {"key": "first_workplace", "text": "你第一份实习/工作的单位是？"},
    {"key": "secret_word", "text": "只有你自己知道的一个词（自定义）"},
]
QUESTION_TEXT = {item["key"]: item["text"] for item in QUESTIONS}

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_TTL_MINUTES = 0  # 0 = 不过期，直到被使用或重新生成
RESET_TICKET_MINUTES = 10
MAX_FAIL_COUNT = 5
LOCK_MINUTES = 15


# ---------- 归一化与哈希 ----------


def normalize_answer(raw: Optional[str]) -> str:
    """统一全角/半角、大小写与空白，避免一个空格导致永远找不回账号。"""
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = re.sub(r"\s+", "", text).strip().lower()
    return text


def normalize_code(raw: Optional[str]) -> str:
    """恢复码归一化为大写去分隔符形式：xj-ab12-cd34 → XJAB12CD34。"""
    return re.sub(r"[^0-9A-Za-z]", "", str(raw or "")).upper()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_code(normalized: str) -> str:
    return _sha256(normalized)


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """生成形如 XJ-7K2M-9QDF 的恢复码，去掉 0/O/1/I 等易混字符。"""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    codes: list[str] = []
    for _ in range(count):
        body = "".join(secrets.choice(alphabet) for _ in range(8))
        codes.append(f"XJ-{body[:4]}-{body[4:]}")
    return codes


def new_reset_ticket() -> tuple[str, str]:
    """返回 (明文票据, 哈希)。明文只回给客户端一次。"""
    token = secrets.token_urlsafe(32)
    return token, _sha256(token)


def hash_ticket(token: str) -> str:
    return _sha256(str(token or "").strip())


# ---------- 设备识别 ----------


def describe_device(user_agent: Optional[str], platform_hint: Optional[str] = None) -> tuple[str, str]:
    """把 UA 压成「浏览器 · 系统」和一个平台枚举，用于设备列表展示。"""
    ua = str(user_agent or "")
    hint = str(platform_hint or "").lower()
    low = ua.lower()

    if "micromessenger" in low:
        browser = "微信内置浏览器"
    elif "edg/" in low:
        browser = "Edge"
    elif "firefox" in low:
        browser = "Firefox"
    elif "chrome" in low or "crios" in low:
        browser = "Chrome"
    elif "safari" in low:
        browser = "Safari"
    elif not ua:
        browser = "未知浏览器"
    else:
        browser = "其他浏览器"

    if "harmonyos" in low or "openharmony" in low:
        system = "HarmonyOS"
    elif "iphone" in low:
        system = "iPhone"
    elif "ipad" in low:
        system = "iPad"
    elif "android" in low:
        system = "Android"
    elif "windows" in low:
        system = "Windows"
    elif "mac os" in low or "macintosh" in low:
        system = "macOS"
    elif "linux" in low:
        system = "Linux"
    else:
        system = "未知系统"

    if hint in ("ios", "android", "web", "miniprogram"):
        platform = hint
    elif "iphone" in low or "ipad" in low:
        platform = "ios"
    elif "android" in low:
        platform = "android"
    else:
        platform = "web"

    return f"{browser} · {system}", platform


def client_ip(request) -> Optional[str]:
    """取真实客户端 IP：反向代理场景优先 X-Forwarded-For 的第一段。"""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64] or None
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()[:64] or None
    return getattr(getattr(request, "client", None), "host", None)


# ---------- 会话 ----------


def open_session(
    db: Session, user: User, request=None, *, platform_hint: Optional[str] = None
) -> tuple[str, AuthSession]:
    """登录成功时开一条会话并签发带 jti 的 token。"""
    from ..security import create_access_token

    user_agent = ""
    if request is not None:
        user_agent = request.headers.get("user-agent", "")[:255]
    device, platform = describe_device(user_agent, platform_hint)
    now = datetime.utcnow()
    jti = new_jti()
    session = AuthSession(
        user_id=user.id,
        jti=jti,
        device=device,
        platform=platform,
        user_agent=user_agent or None,
        ip=client_ip(request),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    token = create_access_token(user.id, user.username, jti=jti)
    return token, session


def active_sessions(db: Session, user_id: int) -> list[AuthSession]:
    now = datetime.utcnow()
    rows = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_seen_at.desc())
    ).all()
    return [row for row in rows if row.expires_at > now]


def get_session_by_jti(db: Session, jti: str) -> Optional[AuthSession]:
    return db.scalar(select(AuthSession).where(AuthSession.jti == jti))


def revoke_session(db: Session, session: AuthSession, reason: str) -> None:
    if session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        session.revoked_reason = reason[:32]


def revoke_other_sessions(db: Session, user_id: int, keep_jti: str, reason: str = "revoked") -> int:
    count = 0
    for row in active_sessions(db, user_id):
        if row.jti == keep_jti:
            continue
        revoke_session(db, row, reason)
        count += 1
    if count:
        db.commit()
    return count


def revoke_all_sessions(db: Session, user_id: int, reason: str = "password_reset") -> int:
    count = 0
    for row in active_sessions(db, user_id):
        revoke_session(db, row, reason)
        count += 1
    if count:
        db.commit()
    return count


def touch_session(db: Session, session: AuthSession, min_interval_seconds: int = 60) -> None:
    """节流更新最后活跃时间：每次请求都写会把会话表变成写入热点。"""
    now = datetime.utcnow()
    last = session.last_seen_at or session.created_at or now
    if (now - last).total_seconds() < min_interval_seconds:
        return
    session.last_seen_at = now
    db.commit()


def purge_expired_sessions(db: Session, user_id: Optional[int] = None) -> int:
    """清理过期会话行，避免表无限增长。"""
    now = datetime.utcnow()
    query = select(AuthSession).where(AuthSession.expires_at <= now)
    if user_id is not None:
        query = query.where(AuthSession.user_id == user_id)
    removed = 0
    for row in db.scalars(query).all():
        db.delete(row)
        removed += 1
    if removed:
        db.commit()
    return removed


def verify_recovery_answer(raw: Optional[str], stored_hash: str) -> bool:
    normalized = normalize_answer(raw)
    if not normalized:
        return False
    return verify_password(normalized, stored_hash)


def hash_recovery_answer(raw: Optional[str]) -> str:
    return hash_password(normalize_answer(raw))
