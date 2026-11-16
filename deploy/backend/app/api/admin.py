"""平台管理后台接口（仅超级管理员可用）。

设计边界
--------
* **身份**：只有 ``User.is_superadmin`` 为真才能访问，普通用户一律 403。
  该字段不通过任何自助注册接口写入，只能由命令行脚本
  （``scripts/create_superadmin.py``）或现有超管授予。
* **不做的事**：不提供「以用户身份登录」（impersonate）和「查看用户隐私数据」。
  管理员能看到的是账号元信息与聚合统计，看不到别人的资料原文、心理数据、答题内容 ——
  这与产品 PRD 里「心理数据隔离、AI 内容可追溯但不越权」的合规口径一致。
* **可审计**：授权 / 取消超管、重置密码都会写一行日志，便于事后追查。
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_superadmin
from ..models import (
    Goal,
    KnowledgePoint,
    Material,
    Mistake,
    QuizAttempt,
    Task,
    User,
)
from ..security import hash_password
from ..services import integrations, tiku_bank

router = APIRouter(prefix="/admin", tags=["admin"])


class SuperadminToggle(BaseModel):
    enabled: bool = Field(description="true=授予超管，false=收回超管")


class PasswordResetOut(BaseModel):
    username: str
    password: str
    note: str


def _log(action: str, actor: User, target: str, extra: str = "") -> None:
    """管理操作留痕：只记账号与动作，不记密码。"""
    stamp = datetime.utcnow().isoformat(timespec="seconds")
    print(f"[admin] {stamp} actor={actor.username} action={action} target={target} {extra}".strip())


def _user_row(user: User, db: Session) -> Dict:
    goals = db.scalar(select(func.count(Goal.id)).where(Goal.user_id == user.id)) or 0
    tasks = db.scalar(select(func.count(Task.id)).where(Task.user_id == user.id)) or 0
    quizzes = db.scalar(select(func.count(QuizAttempt.id)).where(QuizAttempt.user_id == user.id)) or 0
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "school": user.school,
        "is_superadmin": bool(user.is_superadmin),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "goal_count": goals,
        "task_count": tasks,
        "quiz_count": quizzes,
    }


@router.get("/overview")
def overview(
    admin: User = Depends(require_superadmin), db: Session = Depends(get_db)
) -> Dict:
    """管理台首页概览：账号与内容的聚合计数（不含任何个人隐私内容）。"""

    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    return {
        "users": count(User),
        "superadmins": db.scalar(
            select(func.count(User.id)).where(User.is_superadmin.is_(True))
        )
        or 0,
        "goals": count(Goal),
        "knowledge_points": count(KnowledgePoint),
        "materials": count(Material),
        "tasks": count(Task),
        "quiz_attempts": count(QuizAttempt),
        "mistakes": count(Mistake),
        "llm_enabled": bool(settings.LLM_API_KEY),
        "llm_model": getattr(settings, "LLM_MODEL", ""),
        "version": "exam-prep-v1",
    }


@router.get("/users")
def list_users(
    q: str = Query("", description="按用户名/昵称/学校模糊搜索"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Dict:
    stmt = select(User)
    keyword = (q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(like),
                User.nickname.ilike(like),
                User.school.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(User.is_superadmin.desc(), User.id).limit(limit).offset(offset)
    ).all()
    return {
        "total": total,
        "items": [_user_row(user, db) for user in rows],
        "limit": limit,
        "offset": offset,
    }


@router.post("/users/{user_id}/superadmin")
def set_superadmin(
    user_id: int,
    payload: SuperadminToggle,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Dict:
    """授予或收回超管。

    防护：不能收回自己的超管身份（避免把自己锁在门外），
    也至少要保留一个超管账号。
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == admin.id and not payload.enabled:
        raise HTTPException(status_code=400, detail="不能收回自己的超管权限")
    if not payload.enabled:
        remaining = db.scalar(
            select(func.count(User.id)).where(
                User.is_superadmin.is_(True), User.id != target.id
            )
        )
        if not remaining:
            raise HTTPException(status_code=400, detail="系统至少需要保留一个超级管理员")
    target.is_superadmin = bool(payload.enabled)
    db.commit()
    _log("grant_superadmin" if payload.enabled else "revoke_superadmin", admin, target.username)
    return {"id": target.id, "username": target.username, "is_superadmin": bool(target.is_superadmin)}


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
def reset_password(
    user_id: int,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> PasswordResetOut:
    """为指定账号重置密码，返回一次性展示的临时口令。

    临时口令只在这里返回一次，不落日志；用户登录后应自行改密。
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="请到「账号设置」修改自己的密码")
    temp = "Xj" + __import__("secrets").token_urlsafe(9).replace("-", "a").replace("_", "b")
    target.password_hash = hash_password(temp)
    db.commit()
    _log("reset_password", admin, target.username)
    return PasswordResetOut(
        username=target.username,
        password=temp,
        note="临时口令只展示这一次，请通过安全渠道交给对方，并提醒登录后立即改密。",
    )


@router.get("/system")
async def system_status(
    admin: User = Depends(require_superadmin),
) -> Dict:
    """研发视角的依赖探活：数据库、模型、题库、视频源逐项真实状态。"""
    described = integrations.describe_integrations()
    items: List[Dict] = described.get("items", [])

    tiku: Dict = {"configured": tiku_bank.configured(), "status": "unknown"}
    if tiku_bank.configured():
        try:
            health = await tiku_bank.get_client().health()
            tiku.update(
                {
                    "status": "ok" if health.get("ok", True) else "error",
                    "detail": health,
                }
            )
        except Exception as exc:  # noqa: BLE001
            tiku.update({"status": "error", "detail": str(exc)[:160]})
    else:
        tiku["status"] = "not_configured"

    return {
        "integrations": items,
        "tiku": tiku,
        "llm": {
            "enabled": bool(settings.LLM_API_KEY),
            "base_url": settings.LLM_BASE_URL,
            "model": getattr(settings, "LLM_MODEL", ""),
        },
    }
