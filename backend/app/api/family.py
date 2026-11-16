"""家长授权与成长摘要接口。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services import consent

router = APIRouter(tags=["家长授权报告"])


class ConsentIn(BaseModel):
    scope: str = Field(default="parent_report", max_length=32)
    granted: bool = False


@router.get("/goals/{goal_id}/consent")
def get_goal_consent(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_user_goal(goal_id, user, db)
    return consent.consent_dict(consent.get_consent(db, user.id))


@router.post("/goals/{goal_id}/consent")
def set_goal_consent(
    goal_id: int,
    payload: ConsentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_user_goal(goal_id, user, db)
    record = consent.set_consent(db, user.id, payload.scope, payload.granted)
    return consent.consent_dict(record)


@router.get("/goals/{goal_id}/parent-report")
def parent_report(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    record = consent.get_consent(db, user.id)
    if not record or not record.granted:
        raise HTTPException(status_code=403, detail="尚未授权家长查看成长摘要")
    return consent.build_parent_report(db, user, goal)