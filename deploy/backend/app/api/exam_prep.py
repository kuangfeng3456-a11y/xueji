"""备考方案接口：整套方案、某天的三段课表、随堂测与阶段考试。

对应前端「计划 → 备考方案」页，用户点开就能看到：
- 距离考试还有多久、现在处于哪个阶段；
- 第一天上午/下午/晚上分别干什么；
- 每个时段的知识点、真实视频课程、随堂测入口；
- 每个阶段的模考成绩。
"""

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import ExamPrepStage, User
from ..services import exam_prep
from ..services import quiz as quiz_service
from ..services.quiz import generate_quiz, grade_quiz

router = APIRouter(prefix="/goals", tags=["备考方案"])


class PlanBuildIn(BaseModel):
    regenerate: bool = False


class StageExamIn(BaseModel):
    stage_id: int
    count: int = Field(default=6, ge=2, le=12)


class StageExamSubmitIn(BaseModel):
    quiz_id: str
    answers: List[int] = []


@router.get("/{goal_id}/exam-prep")
def get_plan(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """整套备考方案（阶段 + 每日三段课表）。没有就实时生成。"""
    goal = get_user_goal(goal_id, user, db)
    try:
        return exam_prep.build_plan(db, user, goal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{goal_id}/exam-prep/build")
def rebuild_plan(
    goal_id: int,
    payload: PlanBuildIn = Body(default=PlanBuildIn()),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重新生成整套方案（阶段重新切分、课表重排）。"""
    goal = get_user_goal(goal_id, user, db)
    try:
        return exam_prep.build_plan(db, user, goal, regenerate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{goal_id}/exam-prep/day/{day_index}")
async def get_day(
    goal_id: int,
    day_index: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """某一天的完整课表：三段安排 + 知识网络 + 真实视频课程。"""
    goal = get_user_goal(goal_id, user, db)
    try:
        return await exam_prep.day_detail(db, user, goal, day_index)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{goal_id}/exam-prep/stage-exam")
async def start_stage_exam(
    goal_id: int,
    payload: StageExamIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """生成阶段模考试卷：覆盖该阶段全部考点，题目来自统一出题官。"""
    goal = get_user_goal(goal_id, user, db)
    stage = db.get(ExamPrepStage, payload.stage_id)
    if stage is None or stage.user_id != user.id or stage.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="阶段不存在")
    kp_ids = exam_prep.stage_exam_points(db, user, goal, stage.phase)
    if not kp_ids:
        raise HTTPException(status_code=400, detail="该阶段还没有安排知识点")
    try:
        result = await generate_quiz(
            db, user, goal, None, payload.count, kp_ids=kp_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result["stage_id"] = stage.id
    result["stage_title"] = stage.title
    result["target_retention"] = stage.target_retention
    result["kp_count"] = len(kp_ids)
    return result


@router.post("/{goal_id}/exam-prep/stage-exam/submit")
async def submit_stage_exam(
    goal_id: int,
    payload: StageExamSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交阶段模考：判分、补齐详细解析并把成绩落到阶段上。"""
    goal = get_user_goal(goal_id, user, db)
    try:
        result = grade_quiz(db, user, goal, payload.quiz_id, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await quiz_service.enrich_explanations(result.get("wrong") or [])
    total = int(result.get("total") or 0)
    score = int(result.get("score") or 0)
    ratio = (score / total * 100) if total else 0.0
    stage = db.query(ExamPrepStage).filter(
        ExamPrepStage.user_id == user.id,
        ExamPrepStage.goal_id == goal.id,
    ).order_by(ExamPrepStage.start_date).first()
    passed = ratio >= 60
    if stage is not None:
        exam_prep.record_stage_exam(
            db, user, goal, stage.id, score, total, passed, result.get("engine", "rule")
        )
    result["passed"] = passed
    result["pass_rate"] = round(ratio, 1)
    result["stage_id"] = stage.id if stage is not None else None
    return result
