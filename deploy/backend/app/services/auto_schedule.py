"""按剩余时间自动调整今日计划。

用户不需要手动点「重排」：每次进入首页都会检查逾期、空计划与临考冲刺状态，
必要时自动顺延任务、生成今日计划或提高复习密度，并把调整原因返回给前端展示。
"""

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, Task, User
from .planner import build_plan, replan
from .rules import days_left


def _day_tasks(db: Session, user_id: int, goal_id: int, today: date) -> List[Task]:
    return db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal_id,
            Task.day == today,
            Task.status != "skipped",
        ).order_by(Task.priority.desc())
    ).all()


def auto_adjust_today(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    remain = days_left(goal.exam_date, today)
    active = _day_tasks(db, user.id, goal.id, today)
    overdue = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day < today,
        )
    ).all()

    changes: List[dict] = []
    adjusted = False
    summary = ""

    if not active:
        if overdue:
            result = replan(db, user.id, goal, trigger="auto_overdue", today=today)
            changes = result["changes"]
            summary = f"检测到 {len(overdue)} 个逾期任务，已自动顺延并重排今天的学习安排。"
            adjusted = True
        else:
            result = build_plan(db, user.id, goal, days=1, regenerate=False, today=today)
            if result["tasks"]:
                db.commit()
                summary = "今天还没有任务，已根据剩余时间自动生成今日计划。"
                adjusted = True
                changes = [{"kind": "auto_plan", "detail": result["summary"], "task_id": None}]
    elif overdue:
        result = replan(db, user.id, goal, trigger="auto_overdue", today=today)
        changes = result["changes"]
        summary = f"检测到 {len(overdue)} 个逾期任务，已自动重排并优先补上。"
        adjusted = True
    elif remain <= 7:
        has_review = any(task.type == "review" for task in active)
        if not has_review:
            result = replan(db, user.id, goal, trigger="auto_sprint", today=today)
            changes = result["changes"]
            summary = f"距考试只剩 {remain} 天，已自动提高复习密度并插入冲刺复习。"
            adjusted = True

    active = _day_tasks(db, user.id, goal.id, today)
    pending = [task for task in active if task.status == "pending"]
    return {
        "adjusted": adjusted,
        "summary": summary,
        "changes": changes,
        "days_left": remain,
        "force_mode": bool(goal.force_mode),
        "mandatory_remaining": len(pending),
        "sprint_mode": remain <= 7,
    }