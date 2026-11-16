"""收益密度排程预览接口（A3）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services.schedule_preview import schedule_preview

router = APIRouter(tags=["收益密度排程"])


@router.get("/goals/{goal_id}/schedule/preview")
def preview(
    goal_id: int,
    limit: int = Query(default=8, ge=3, le=20),
    minutes: int = Query(default=20, ge=5, le=120),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return schedule_preview(db, user, goal, limit, minutes)