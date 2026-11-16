"""反向教学接口：费曼检验场、反向判卷、错误免疫。

三者共用一条原则：判定基准在服务端预置，模型只辅助生成与判命中，
所以接口返回里都带 `engine` 字段，说明这一次是模型参与还是规则兜底。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services import reverse_teaching as svc

router = APIRouter(prefix="/teaching", tags=["反向教学"])


class GoalIn(BaseModel):
    goal_id: int
    kp_id: Optional[int] = None


class ReverseStartIn(GoalIn):
    difficulty: str = Field(default="normal", pattern="^(easy|normal|hard)$")
    cause: Optional[str] = None


class FeynmanSubmitIn(BaseModel):
    session_id: int
    speech: str = Field(min_length=1, max_length=2000)
    speech_mode: str = Field(default="text", pattern="^(text|voice)$")


class ReverseGradeIn(BaseModel):
    task_id: int
    picked_step: int = Field(ge=1, le=8)
    picked_type: str = Field(min_length=1, max_length=16)
    fix_text: str = Field(default="", max_length=1000)


class DrillIn(BaseModel):
    goal_id: int
    fingerprint: Optional[str] = Field(default=None, max_length=128)
    kp_id: Optional[int] = None


class DrillAnswerIn(BaseModel):
    drill_id: int
    picked: str = Field(min_length=1, max_length=2)


def _bad(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/feynman/start")
async def feynman_start(
    payload: GoalIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(payload.goal_id, user, db)
    try:
        return await svc.start_feynman(db, user, goal, payload.kp_id)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/feynman/submit")
async def feynman_submit(
    payload: FeynmanSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return await svc.submit_feynman(db, user, payload.session_id, payload.speech, payload.speech_mode)
    except ValueError as exc:
        raise _bad(exc)


@router.get("/feynman/profile")
def feynman_profile(
    goal_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return svc.feynman_profile(db, user, goal)


@router.get("/feynman/history")
def feynman_history(
    goal_id: int = Query(..., ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return {"items": svc.feynman_history(db, user, goal, limit)}


@router.post("/reverse/start")
async def reverse_start(
    payload: ReverseStartIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(payload.goal_id, user, db)
    try:
        return await svc.start_reverse(db, user, goal, payload.kp_id, payload.difficulty, payload.cause)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/reverse/grade")
async def reverse_grade(
    payload: ReverseGradeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return await svc.grade_reverse(
            db, user, payload.task_id, payload.picked_step, payload.picked_type, payload.fix_text
        )
    except ValueError as exc:
        raise _bad(exc)


@router.get("/reverse/profile")
def reverse_profile(
    goal_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return svc.reverse_profile(db, user, goal)


@router.get("/reverse/history")
def reverse_history(
    goal_id: int = Query(..., ge=1),
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return {"items": svc.reverse_history(db, user, goal, limit)}


@router.get("/immune/fingerprints")
def immune_fingerprints(
    goal_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return svc.fingerprints(db, user, goal)


@router.post("/immune/drill")
async def immune_drill(
    payload: DrillIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(payload.goal_id, user, db)
    try:
        return await svc.make_drill(db, user, goal, payload.fingerprint, payload.kp_id)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/immune/answer")
def immune_answer(
    payload: DrillAnswerIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return svc.answer_drill(db, user, payload.drill_id, payload.picked)
    except ValueError as exc:
        raise _bad(exc)


@router.get("/immune/profile")
def immune_profile(
    goal_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return svc.immune_profile(db, user, goal)
