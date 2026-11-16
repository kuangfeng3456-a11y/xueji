"""v2.0 P1 增强接口：蒙特卡洛区间、阶段状态机、疲劳与认知负荷。"""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import (
    FocusSession,
    KnowledgePoint,
    LearningEvent,
    Mastery,
    Mistake,
    ReviewCard,
    Task,
    User,
)
from ..services.advanced import (
    cognitive_load,
    fatigue_index,
    monte_carlo_exam_score,
    monte_carlo_forecast,
    phase_for,
)
from ..services.rules import days_left

router = APIRouter(tags=["P1 诊断增强"])


def _facts(db: Session, user: User, goal, today: date):
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id, Mastery.kp_id.in_([p.id for p in points] or [0])
        )
    ).all()
    current = sum(row.value for row in rows) / len(rows) if rows else 0.0
    grouped = db.execute(
        select(LearningEvent.kp_id, func.count(LearningEvent.id))
        .where(
            LearningEvent.user_id == user.id,
            LearningEvent.goal_id == goal.id,
            LearningEvent.event_type == "answer",
        )
        .group_by(LearningEvent.kp_id)
    ).all()
    n_eff = (sum(count for _, count in grouped) / len(grouped)) if grouped else 0.0
    uncertainty = ((current * (1 - current)) / (n_eff + 2)) ** 0.5
    start = today - timedelta(days=28)
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day >= start,
            Task.day <= today,
        )
    ).all()
    judged = [task for task in tasks if task.status != "skipped"]
    done = [task for task in judged if task.status == "done"]
    rate = (len(done) / len(judged)) if judged else 0.0
    return current, uncertainty, round(rate * 0.005, 4), rate, today


@router.get("/goals/{goal_id}/forecast/montecarlo")
def montecarlo(
    goal_id: int,
    target: float = Query(default=0.7, ge=0.1, le=100.0),
    days: Optional[int] = Query(default=None, ge=0, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    today = date.today()
    _, _, _, rate, _ = _facts(db, user, goal, today)
    horizon = days if days is not None else days_left(goal.exam_date, today)

    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    point_ids = [point.id for point in points] or [0]
    mastery_rows = db.scalars(
        select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id.in_(point_ids))
    ).all()
    mastery_map = {row.kp_id: row.value for row in mastery_rows}
    counts = dict(
        db.execute(
            select(LearningEvent.kp_id, func.count(LearningEvent.id))
            .where(
                LearningEvent.user_id == user.id,
                LearningEvent.kp_id.in_(point_ids),
            )
            .group_by(LearningEvent.kp_id)
        ).all()
    )
    card_map = {
        row.kp_id: row
        for row in db.scalars(
            select(ReviewCard).where(
                ReviewCard.user_id == user.id, ReviewCard.kp_id.in_(point_ids)
            )
        ).all()
    }
    knowledge = []
    for point in points:
        mastery = float(mastery_map.get(point.id, 0.0))
        n_eff = float(counts.get(point.id, 0) or 0)
        uncertainty = ((mastery * (1 - mastery)) / (n_eff + 2)) ** 0.5
        card = card_map.get(point.id)
        knowledge.append(
            {
                "kp_id": point.id,
                "weight": max(float(point.weight), 0.05),
                "mastery": mastery,
                "uncertainty": max(uncertainty, 0.02),
                "stability_days": float(card.stability) if card else 1.0,
            }
        )

    target_score = target * 100 if target <= 1 else target
    result = monte_carlo_exam_score(
        knowledge,
        completion_rate=rate,
        tasks_per_day=3,
        eta=0.18,
        days_left_count=horizon,
        target_score=target_score,
    )
    result["current_mastery"] = round(
        sum(item["weight"] * item["mastery"] for item in knowledge)
        / max(sum(item["weight"] for item in knowledge), 1e-6),
        4,
    ) if knowledge else 0.0
    result["completion_rate_28d"] = round(rate, 3)
    result["knowledge_count"] = len(knowledge)
    return result


@router.get("/goals/{goal_id}/phase")
def phase(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return phase_for(days_left(goal.exam_date, date.today()))


@router.get("/goals/{goal_id}/fatigue")
def fatigue(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    today = date.today()
    start_3d = today - timedelta(days=3)
    start_14d = today - timedelta(days=14)

    sessions_3d = db.scalars(
        select(FocusSession).where(
            FocusSession.user_id == user.id,
            FocusSession.goal_id == goal.id,
            FocusSession.started_at >= datetime.combine(start_3d, datetime.min.time()),
        )
    ).all()
    focus_minutes = sum(max(item.actual_minutes, 0) for item in sessions_3d)
    leaves = sum(max(item.leaves, 0) for item in sessions_3d)

    mistakes_3d = db.scalar(
        select(func.count(Mistake.id)).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= datetime.combine(start_3d, datetime.min.time()),
        )
    ) or 0
    mistakes_14d = db.scalar(
        select(func.count(Mistake.id)).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= datetime.combine(start_14d, datetime.min.time()),
        )
    ) or 0

    done_days = set(
        db.scalars(
            select(Task.day).where(
                Task.user_id == user.id,
                Task.goal_id == goal.id,
                Task.status == "done",
            )
        ).all()
    )
    streak = 0
    cursor = today
    if cursor not in done_days:
        cursor = today - timedelta(days=1)
    while cursor in done_days:
        streak += 1
        cursor -= timedelta(days=1)

    tasks_today = db.scalars(
        select(Task).where(
            Task.user_id == user.id, Task.goal_id == goal.id, Task.day == today
        )
    ).all()
    planned = sum(task.duration_min for task in tasks_today)
    attempts = max(len(tasks_today), 1)
    recent_error_rate = min(1.0, int(mistakes_3d) / attempts)
    baseline_error_rate = min(1.0, int(mistakes_14d) / max(attempts, 1))

    fatigue_data = fatigue_index(
        interruptions=leaves,
        sessions=len(sessions_3d),
        leave_minutes=leaves * 2.0,
        focus_minutes=float(focus_minutes),
        recent_error_rate=recent_error_rate,
        baseline_error_rate=baseline_error_rate,
        streak_days=streak,
    )
    load = cognitive_load(
        planned,
        goal.daily_minutes,
        fatigue_data["index"],
        recent_error_rate,
        avg_difficulty=3.0,
    )
    return {
        "fatigue": fatigue_data,
        "load": load,
        "planned_minutes": planned,
        "daily_minutes": goal.daily_minutes,
        "inputs": {
            "focus_sessions_3d": len(sessions_3d),
            "focus_minutes_3d": focus_minutes,
            "leaves_3d": leaves,
            "mistakes_3d": int(mistakes_3d),
            "mistakes_14d": int(mistakes_14d),
            "streak_days": streak,
        },
    }