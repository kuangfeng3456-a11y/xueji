from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Goal, User
from ..schemas import AskIn, AskOut
from ..services.qa import answer_question

router = APIRouter(prefix="/coach", tags=["语音问答"])


@router.post("/ask", response_model=AskOut)
async def ask(
    payload: AskIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AskOut:
    goal: Optional[Goal] = None
    if payload.goal_id is not None:
        goal = db.get(Goal, payload.goal_id)
        if goal and goal.user_id != user.id:
            goal = None
    if goal is None:
        goal = db.scalar(
            select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc()).limit(1)
        )
    result = await answer_question(db, user, goal, payload.question)
    return AskOut(**result)