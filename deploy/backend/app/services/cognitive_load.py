"""认知负荷调节器：根据学习状态动态调整任务难度与数量。"""

import json
from datetime import date, timedelta
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, Mistake, Task, User
from .evidence import record_evidence
from .insights import build_fatigue
from .readiness import _rest_today, compute_readiness
from .rules import clamp


def compute_load(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    readiness = compute_readiness(db, user, goal, today)
    fatigue = build_fatigue(db, user.id, goal.id, today)
    today_tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        )
    ).all()
    today_minutes = sum(task.duration_min for task in today_tasks)
    since = today - timedelta(days=6)
    mistakes = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= since,
        )
    ).all()
    done = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "done",
            Task.day >= since,
        )
    ).all()
    wrong_ratio = min(1.0, len(mistakes) / max(1, len(done) + len(mistakes)))

    load = fatigue["score"] * 0.55
    if goal.daily_minutes:
        load += max(0.0, today_minutes / goal.daily_minutes - 1) * 35
    load += wrong_ratio * 25
    score = int(round(clamp(load, 0, 100)))

    if score >= 80:
        level = "overload"
        advice = "认知负荷过高：今天只保留 1 个最轻任务，优先恢复，不做新难题。"
        recommended_tasks = 1
        recommended_minutes = min(30, max(15, goal.daily_minutes // 3))
    elif score >= 55:
        level = "high"
        advice = "负荷偏高：把任务拆成 15 分钟小块，先做复习，难题放到明天。"
        recommended_tasks = max(1, min(2, len(today_tasks)))
        recommended_minutes = max(20, goal.daily_minutes // 2)
    elif score >= 30:
        level = "optimal"
        advice = "负荷适中：保持当前难度，按计划完成即可。"
        recommended_tasks = len(today_tasks) or 3
        recommended_minutes = goal.daily_minutes
    else:
        level = "low"
        advice = "负荷偏低：可以加入 1 道迁移题或挑战题，适当提高难度。"
        recommended_tasks = (len(today_tasks) or 2) + 1
        recommended_minutes = min(180, goal.daily_minutes + 20)

    return {
        "score": score,
        "level": level,
        "factors": [
            f"疲劳指数 {fatigue['score']}",
            f"今日任务 {len(today_tasks)} 个 / {today_minutes} 分钟",
            f"近 7 天错题率 {round(wrong_ratio * 100)}%",
            f"准备度 {readiness['score']}%",
        ],
        "advice": advice,
        "recommended_tasks": recommended_tasks,
        "recommended_minutes": recommended_minutes,
    }


def apply_load(
    db: Session, user: User, goal: Goal, action: str = "auto", today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    before = compute_load(db, user, goal, today)
    if action == "auto":
        if before["level"] in ("overload", "high"):
            action = "reduce"
        elif before["level"] == "low":
            action = "increase"
        else:
            action = "keep"

    changes = []
    if action == "reduce":
        moved, changes = _rest_today(db, user, goal, today)
        if moved:
            message = f"已按认知负荷降载：顺延 {moved} 个任务，保留 1 个最轻任务。"
        else:
            message = "当前任务已足够精简，保留 1 个最小任务即可，先恢复状态。"
    elif action == "increase":
        db.add(
            Task(
                user_id=user.id,
                goal_id=goal.id,
                day=today,
                title="迁移挑战：换情境应用",
                type="practice",
                duration_min=20,
                status="pending",
                reason="认知负荷偏低，系统自动加入 1 道迁移/挑战任务，训练陌生情境应用。",
                priority=2.8,
                source="cognitive_load",
            )
        )
        db.commit()
        message = "已加入 1 个 20 分钟迁移挑战任务。"
        changes = [{"kind": "increase", "detail": "加入迁移挑战任务", "task_id": None}]
    else:
        message = "当前认知负荷适中，保持现有难度即可。"

    record_evidence(
        db,
        user.id,
        goal.id,
        "cognitive_load",
        f"认知负荷调节（{action}）",
        {"before": before, "action": action},
        message,
        engine="rule",
    )
    db.commit()
    after = compute_load(db, user, goal, today)
    return {
        "action": action,
        "before": before,
        "after": after,
        "changes": changes,
        "message": message,
    }