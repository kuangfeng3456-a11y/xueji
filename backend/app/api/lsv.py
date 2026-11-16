"""学习者状态向量（LSV）接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services.lsv import build_lsv

router = APIRouter(tags=["学习者状态向量"])


@router.get("/goals/{goal_id}/lsv")
def lsv_snapshot(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return build_lsv(db, user, goal)