"""考前冲刺模拟器：按剩余时间预测考试日掌握度，并反推所需每日时长。"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, User

DAILY_COVER_POINTS = 20
GAIN_PER_TOUCH = 0.12
DAILY_FORGET = 0.995


def _simulate(
    values: List[float], weights: List[float], daily_minutes: int, days: int, today: date
) -> Tuple[float, List[Dict]]:
    mastery = list(values)
    if not mastery:
        return 0.0, []
    curve: List[Dict] = []
    step = max(1, days // 10)
    cover = max(1, int(daily_minutes // DAILY_COVER_POINTS))
    for offset in range(1, days + 1):
        for index in range(len(mastery)):
            mastery[index] = max(0.0, mastery[index] * DAILY_FORGET)
        order = sorted(
            range(len(mastery)),
            key=lambda index: (1 - mastery[index]) * weights[index],
            reverse=True,
        )[:cover]
        for index in order:
            mastery[index] = min(1.0, mastery[index] + GAIN_PER_TOUCH * (1 - mastery[index]))
        if offset % step == 0 or offset == days:
            curve.append(
                {
                    "day": today + timedelta(days=offset),
                    "mastery": round(sum(mastery) / len(mastery), 4),
                }
            )
    return round(sum(mastery) / len(mastery), 4), curve


def build_forecast(
    db: Session,
    user: User,
    goal: Goal,
    daily_minutes: Optional[int] = None,
    today: Optional[date] = None,
) -> Dict:
    today = today or date.today()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    leaves = [point for point in points if point.id not in {p.parent_id for p in points if p.parent_id}]
    if not leaves:
        leaves = points
    if not leaves:
        return {
            "current_mastery": 0.0,
            "projected_mastery": 0.0,
            "days_left": max((goal.exam_date - today).days, 0),
            "target_mastery": 0.7,
            "required_daily_minutes": None,
            "recommendation": "还没有知识点，先导入资料再模拟冲刺效果。",
            "curve": [],
            "scenarios": [],
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
    base_daily = daily_minutes or goal.daily_minutes
    target = min(0.9, max(0.7, current + 0.2))
    projected, curve = _simulate(values, weights, base_daily, days, today)

    scenarios = []
    for label, daily in (
        ("当前节奏", base_daily),
        ("减负 -30 分钟", max(20, base_daily - 30)),
        ("冲刺 +30 分钟", min(600, base_daily + 30)),
    ):
        value, _ = _simulate(values, weights, daily, days, today)
        scenarios.append(
            {
                "label": label,
                "daily_minutes": daily,
                "projected_mastery": value,
                "feasible": value >= target,
            }
        )

    required: Optional[int] = None
    for candidate in range(20, 601, 10):
        value, _ = _simulate(values, weights, candidate, days, today)
        if value >= target:
            required = candidate
            break

    if projected >= target:
        recommendation = (
            f"按当前每天 {base_daily} 分钟，预计考试日平均掌握度可达 {round(projected * 100)}%，"
            f"高于目标 {round(target * 100)}%，保持节奏即可。"
        )
    elif required is not None:
        recommendation = (
            f"按当前节奏预计只能达到 {round(projected * 100)}%，"
            f"若想达到 {round(target * 100)}%，建议每天提高到约 {required} 分钟，"
            f"系统会自动重排后续任务。"
        )
    else:
        recommendation = (
            f"即使每天 600 分钟，预计也只能达到 {round(projected * 100)}%。"
            "建议缩减知识点范围，优先保住高权重与已掌握部分，或与老师确认取舍。"
        )

    return {
        "current_mastery": current,
        "projected_mastery": projected,
        "days_left": max((goal.exam_date - today).days, 0),
        "target_mastery": round(target, 4),
        "required_daily_minutes": required,
        "recommendation": recommendation,
        "curve": curve,
        "scenarios": scenarios,
    }