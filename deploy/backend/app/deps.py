from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuthSession, Goal, User
from .security import decode_token
from .services.account_security import get_session_by_jti, touch_session

bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(credentials: Optional[HTTPAuthorizationCredentials], request: Request) -> Optional[str]:
    """取 token：优先自定义头 X-Auth-Token。

    部署网关会把 Authorization 头改写成平台自身的令牌（实测长度都会变），
    因此前端附带 X-Auth-Token 作为双保险；两者都在时以自定义头为准。
    """
    custom = request.headers.get("x-auth-token", "").strip()
    if custom:
        return custom
    if credentials is not None:
        return credentials.credentials
    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """校验 token 与会话。

    除了签名与过期，还要确认这枚 token 对应的会话没有被撤销 ——
    「退出其他设备」和「改密后其它设备掉线」靠的就是这一步。
    """
    token = _extract_token(credentials, request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭据已升级，请重新登录"
        )
    session = get_session_by_jti(db, jti)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")
    if session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="该设备已退出登录，请重新登录")
    if session.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    touch_session(db, session)
    # 供端点识别「当前设备」，避免再解一次 token
    setattr(user, "_auth_session", session)
    return user


def current_session(user: User) -> Optional[AuthSession]:
    return getattr(user, "_auth_session", None)


def get_user_goal(goal_id: int, user: User, db: Session) -> Goal:
    goal = db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="目标不存在")
    return goal


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    """平台超级管理员校验（开发者账号）。

    与「班级角色」是两套东西：班级 role 只在某个班级内生效，
    超管是平台级身份，用于访问 /api/admin 与研发内部工具。
    任何未授权用户一律 403，且不透露对方是否为管理员。
    """
    if not getattr(user, "is_superadmin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return user
