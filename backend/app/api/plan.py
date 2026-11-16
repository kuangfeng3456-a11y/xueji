import json
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.planner_agent import planner_generate
from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Goal, KnowledgePoint, LearningEvent, Mastery, ReplanLog, Task, User
from ..schemas import AutoAdjustOut, PlanRequest, PlanResult, ReplanResult, TaskOut, TaskStatusIn
from ..services.auto_schedule import auto_adjust_today
from ..services.learning_events import record_event
from ..services.planner import build_plan, replan, task_to_dict
from ..services.rules import (
    days_left,
    mastery_uncertainty,
    retention,
    stability_for_stage,
    task_tiers,
    task_why,
)
from ..cache import cache

router = APIRouter(prefix="/goals", tags=["计划与任务"])


def _kp_map(db: Session, goal_id: int) -> dict:
    return {
        point.id: point
        for point in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    }


def _list_tasks(
    db: Session, user_id: int, goal_id: int, start: Optional[date], end: Optional[date]
) -> List[TaskOut]:
    query = select(Task).where(Task.user_id == user_id, Task.goal_id == goal_id)
    if start is not None:
        query = query.where(Task.day >= start)
    if end is not None:
        query = query.where(Task.day <= end)
    tasks = db.scalars(query.order_by(Task.day.asc(), Task.priority.desc())).all()
    kp_map = _kp_map(db, goal_id)
    return [TaskOut(**task_to_dict(task, kp_map)) for task in tasks]


@router.post("/{goal_id}/plan", response_model=PlanResult)
async def generate_plan(
    goal_id: int,
    payload: PlanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanResult:
    goal = get_user_goal(goal_id, user, db)
    result = await planner_generate(
        db, user.id, goal, days=payload.days, regenerate=payload.regenerate
    )
    db.commit()
    cache.delete(f"dashboard:{user.id}:{goal.id}")
    return PlanResult(
        tasks=[TaskOut(**task) for task in result["tasks"]],
        summary=result["summary"],
        days=result["days"],
        total_minutes=result["total_minutes"],
    )


@router.get("/{goal_id}/tasks", response_model=List[TaskOut])
def list_tasks(
    goal_id: int,
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[TaskOut]:
    goal = get_user_goal(goal_id, user, db)
    return _list_tasks(db, user.id, goal.id, start, end)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task_status(
    task_id: int,
    payload: TaskStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskOut:
    task = db.get(Task, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    goal = db.get(Goal, task.goal_id)
    if payload.status == "skipped" and goal and goal.force_mode:
        raise HTTPException(
            status_code=400,
            detail="强制学习模式已开启：任务不能跳过，请进入「强制学习」完成或中止并记录违约",
        )
    task.status = payload.status
    if payload.skip_reason is not None:
        task.skip_reason = payload.skip_reason
    if payload.feedback is not None:
        task.feedback = payload.feedback
    if payload.status == "done":
        task.done_at = datetime.utcnow()
    else:
        task.done_at = None
    if payload.status in ("done", "skipped"):
        record_event(
            db,
            user.id,
            task.goal_id,
            "task_done" if payload.status == "done" else "task_skip",
            task.kp_id,
            {
                "task_id": task.id,
                "title": task.title,
                "type": task.type,
                "duration_min": task.duration_min,
                "feedback": task.feedback,
            },
        )
    db.commit()
    db.refresh(task)
    cache.delete(f"dashboard:{user.id}:{task.goal_id}")
    return TaskOut(**task_to_dict(task, _kp_map(db, task.goal_id)))


class TaskMinutesIn(BaseModel):
    minutes: int = Field(ge=3, le=240)


@router.get("/{goal_id}/tasks/{task_id}/why")
def task_why_detail(
    goal_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """反事实 Why：给出任务价值、收益密度、期望增益与任务三档，数字全部由规则计算。"""
    goal = get_user_goal(goal_id, user, db)
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id or task.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    point = db.get(KnowledgePoint, task.kp_id) if task.kp_id else None
    mastery = (
        db.scalar(
            select(Mastery).where(
                Mastery.user_id == user.id, Mastery.kp_id == task.kp_id
            )
        )
        if task.kp_id
        else None
    )
    value = mastery.value if mastery else 0.0
    stage = mastery.review_stage if mastery else 0
    today = date.today()
    last_day = mastery.updated_at.date() if mastery and mastery.updated_at else today
    stability = stability_for_stage(stage)
    retention_now = retention(max(0, (today - last_day).days), stability)
    evidence = (
        db.scalar(
            select(func.count(LearningEvent.id)).where(
                LearningEvent.user_id == user.id,
                LearningEvent.kp_id == task.kp_id,
                LearningEvent.event_type == "answer",
            )
        )
        if task.kp_id
        else 0
    ) or 0
    uncertainty = mastery_uncertainty(value, float(evidence))
    remain = days_left(goal.exam_date, today)
    why = task_why(
        point.weight if point else 1.0,
        value,
        retention_now,
        uncertainty,
        remain,
        task.type,
        task.duration_min,
        1.0,
        0,
        stability,
    )
    return {
        "task_id": task.id,
        "title": task.title,
        "reason": task.reason,
        "retention_now": retention_now,
        "stability_days": stability,
        "tiers": task_tiers(task.duration_min),
        "why": why,
    }


@router.post("/{goal_id}/tasks/{task_id}/minutes", response_model=TaskOut)
def set_task_minutes(
    goal_id: int,
    task_id: int,
    payload: TaskMinutesIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskOut:
    """任务弹性阶梯：按标准/精简/最小档调整分钟数，降档优先于删除。"""
    goal = get_user_goal(goal_id, user, db)
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id or task.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    before = task.duration_min
    task.duration_min = payload.minutes
    record_event(
        db,
        user.id,
        task.goal_id,
        "task_tier",
        task.kp_id,
        {"task_id": task.id, "before": before, "after": payload.minutes},
    )
    db.commit()
    db.refresh(task)
    cache.delete(f"dashboard:{user.id}:{task.goal_id}")
    return TaskOut(**task_to_dict(task, _kp_map(db, task.goal_id)))


@router.post("/{goal_id}/auto-adjust", response_model=AutoAdjustOut)
def trigger_auto_adjust(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AutoAdjustOut:
    """立即按剩余时间自动调整：顺延逾期、补今日计划或进入冲刺复习。"""
    goal = get_user_goal(goal_id, user, db)
    result = auto_adjust_today(db, user, goal)
    cache.delete(f"dashboard:{user.id}:{goal.id}")
    return AutoAdjustOut(**result)


@router.post("/{goal_id}/replan", response_model=ReplanResult)
async def trigger_replan(
    goal_id: int,
    trigger: str = Query(default="manual", max_length=32),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReplanResult:
    goal = get_user_goal(goal_id, user, db)
    result = replan(db, user.id, goal, trigger=trigger)
    cache.delete(f"dashboard:{user.id}:{goal.id}")
    return ReplanResult(
        trigger=result["trigger"],
        changes=result["changes"],
        tasks=[TaskOut(**task) for task in result["tasks"]],
    )


@router.get("/{goal_id}/replan-logs")
def list_replan_logs(
    goal_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[dict]:
    goal = get_user_goal(goal_id, user, db)
    logs = db.scalars(
        select(ReplanLog)
        .where(ReplanLog.user_id == user.id, ReplanLog.goal_id == goal.id)
        .order_by(ReplanLog.created_at.desc())
        .limit(limit)
    ).all()
    result = []
    for log in logs:
        try:
            changes = json.loads(log.changes)
        except Exception:
            changes = []
        result.append(
            {
                "id": log.id,
                "trigger": log.trigger,
                "changes": changes,
                "created_at": log.created_at.isoformat(),
            }
        )
    return result