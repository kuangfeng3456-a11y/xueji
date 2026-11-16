"""苏格拉底导师、复述检查与学习资源工厂接口。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services import tutor

router = APIRouter(tags=["AI 导师与资源工厂"])


class SocraticIn(BaseModel):
    kp_id: int
    message: str = Field(default="", max_length=500)
    mode: str = Field(default="hint", max_length=16)
    level: str = Field(default="direction", max_length=16)


class RecallIn(BaseModel):
    kp_id: int
    recall: str = Field(default="", max_length=1000)


class ResourceIn(BaseModel):
    kp_id: int
    resource_type: str = Field(default="flashcard", max_length=16)
    count: int = Field(default=3, ge=1, le=5)


@router.post("/goals/{goal_id}/socratic")
async def socratic(
    goal_id: int,
    payload: SocraticIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return await tutor.socratic_reply(
        db, user, goal, payload.kp_id, payload.message, payload.mode, payload.level
    )


@router.post("/goals/{goal_id}/socratic/recall")
def recall(
    goal_id: int,
    payload: RecallIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return tutor.recall_check(db, user, goal, payload.kp_id, payload.recall)


@router.post("/goals/{goal_id}/resources/generate")
async def resources(
    goal_id: int,
    payload: ResourceIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return await tutor.generate_resources(
        db, user, goal, payload.kp_id, payload.resource_type, payload.count
    )