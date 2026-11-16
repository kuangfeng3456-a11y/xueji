from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Goal, User
from ..services import module_ai

router = APIRouter(prefix="/module-ai", tags=["模块大模型"])


class ModuleAiIn(BaseModel):
    goal_id: Optional[int] = None


def _resolve_goal(db: Session, user: User, goal_id: Optional[int]) -> Optional[Goal]:
    if goal_id:
        goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
        if not goal:
            raise HTTPException(status_code=404, detail="目标不存在")
        return goal
    return db.scalar(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc()).limit(1)
    )


@router.get("/list")
def modules(user: User = Depends(get_current_user)) -> dict:
    return {"modules": module_ai.module_list(), "total": len(module_ai.MODULES)}


@router.post("/{module}")
async def generate(
    module: str,
    payload: ModuleAiIn = ModuleAiIn(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if module not in module_ai.MODULES:
        raise HTTPException(status_code=404, detail="该模块暂未配置模型能力")
    goal = _resolve_goal(db, user, payload.goal_id)
    try:
        return await module_ai.generate(module, db, user, goal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))