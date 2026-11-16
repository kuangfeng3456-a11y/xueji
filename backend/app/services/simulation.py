"""未来模拟实验室：比较多种学习策略的结果区间与负荷。"""

from datetime import date, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, Task, User
from .forecast import DAILY_COVER_POINTS, DAILY_FORGET, GAIN_PER_TOUCH
from .rules import clamp


def _leaves(db: Session, goal_id: int) -> List[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    return [point for point in points if point.id not in parent_ids] or points


def _simulate(
    values: List[float],
    weights: List[float],
    daily_minutes: int,
    days: int,
    repair_first: bool,
) -> float:
    mastery = list(values)
    if not mastery:
        return 0.0
    cover = max(1, int(daily_minutes // DAILY_COVER_POINTS))
    for _ in range(days):
        for index in range(len(mastery)):
            mastery[index] = max(0.0, mastery[index] * DAILY_FORGET)
        order = sorted(
            range(len(mastery)),
            key=lambda index: (
                ((1 - mastery[index]) ** 2 if repair_first else (1 - mastery[index]))
                * weights[index]
            ),
            reverse=True,
        )[:cover]
        for index in order:
            mastery[index] = min(1.0, mastery[index] + GAIN_PER_TOUCH * (1 - mastery[index]))
    return round(sum(mastery) / len(mastery), 4)


def build_simulation(
    db: Session, user: User, goal: Goal, today: date = None
) -> Dict:
    today = today or date.today()
    leaves = _leaves(db, goal.id)
    if not leaves:
        return {
            "current_mastery": 0.0,
            "days_left": max((goal.exam_date - today).days, 0),
            "target_mastery": 0.7,
            "uncertainty": "还没有知识点，无法模拟。",
            "plans": [],
            "recommendation": "先导入知识点再模拟。",
        }
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id,
            Mastery.kp_id.in_([point.id for point in leaves]),
        )
    ).all()
    mastery_map = {row.kp_id: row.value for row in rows}
    values = [mastery_map.get(point.id, 0.0) for point in leaves]
    weights = [max(point.weight, 0.1) for point in leaves]
    current = round(sum(values) / len(values), 4)

    days = max((goal.exam_date - today).days, 1)
    target = min(0.9, max(0.7, current + 0.2))
    pending = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day >= today,
        )
    ).all()
    pending_minutes = sum(task.duration_min for task in pending)

    specs = [
        ("keep", "维持现状", goal.daily_minutes, False),
        ("more_time", "增加时间", min(600, goal.daily_minutes + 30), False),
        ("repair", "优先修复漏洞", goal.daily_minutes, True),
        ("combo", "修复 + 加时", min(600, goal.daily_minutes + 30), True),
    ]
    plans = []
    for key, label, daily, repair_first in specs:
        projected = _simulate(values, weights, daily, days, repair_first)
        load_ratio = round(pending_minutes / max(1, days * daily), 4)
        if projected < target:
            risk_level = "high"
        elif projected < target + 0.08:
            risk_level = "medium"
        else:
            risk_level = "low"
        assumptions = [
            f"每天约覆盖 {max(1, int(daily // DAILY_COVER_POINTS))} 个知识点",
            "每次覆盖向 1.0 靠近 12%",
            "未复习知识点每天衰减 0.5%",
        ]
        if repair_first:
            assumptions.append("优先选择（1-掌握度）²×权重 更高的薄弱点")
        plans.append(
            {
                "key": key,
                "label": label,
                "daily_minutes": daily,
                "projected_mastery": projected,
                "low": round(clamp(projected - 0.04, 0, 1), 4),
                "high": round(clamp(projected + 0.04, 0, 1), 4),
                "load_ratio": load_ratio,
                "risk_level": risk_level,
                "assumptions": assumptions,
            }
        )

    best = max(plans, key=lambda plan: plan["projected_mastery"])
    feasible = [plan for plan in plans if plan["load_ratio"] <= 1.25]
    if feasible:
        recommended = max(feasible, key=lambda plan: plan["projected_mastery"])
    else:
        recommended = best
    recommendation = (
        f"推荐「{recommended['label']}」：预计考试日平均掌握度 "
        f"{round(recommended['projected_mastery'] * 100)}%"
        f"（区间 {round(recommended['low'] * 100)}%–{round(recommended['high'] * 100)}%），"
        f"每日 {recommended['daily_minutes']} 分钟，负荷 {round(recommended['load_ratio'] * 100)}%。"
    )
    return {
        "current_mastery": current,
        "days_left": max((goal.exam_date - today).days, 0),
        "target_mastery": round(target, 4),
        "uncertainty": "掌握度预测为区间估计，受执行率、题目难度与遗忘速度影响，不构成成绩保证。",
        "plans": plans,
        "recommendation": recommendation,
    }