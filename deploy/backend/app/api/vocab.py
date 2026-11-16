"""词汇单词卡接口：按知识点取词表、逐词记录学习结果、一轮结束汇总掌握度。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services.vocab import build_session, finish_session, record_review

router = APIRouter(prefix="/goals/{goal_id}/vocab", tags=["词汇单词卡"])


class VocabReviewIn(BaseModel):
    kp_id: int
    word: str = Field(min_length=1, max_length=64)
    action: str = Field(pattern="^(known|fuzzy|unknown)$")


class VocabFinishIn(BaseModel):
    kp_id: int
    known: int = Field(default=0, ge=0)
    fuzzy: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


@router.get("")
def session(
    goal_id: int,
    kp_id: int = Query(..., ge=1),
    limit: int = Query(default=20, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    try:
        return build_session(db, user.id, goal.id, kp_id, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/review")
def review(
    goal_id: int,
    payload: VocabReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    try:
        return record_review(db, user.id, goal.id, payload.kp_id, payload.word, payload.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/finish")
def finish(
    goal_id: int,
    payload: VocabFinishIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    try:
        return finish_session(
            db, user.id, goal.id, payload.kp_id, payload.known, payload.fuzzy, payload.unknown
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
