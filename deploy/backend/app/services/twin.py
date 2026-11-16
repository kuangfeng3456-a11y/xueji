"""学习数字孪生：知识矩阵、错因分布、行为趋势与策略偏好。"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Goal,
    KnowledgeGap,
    KnowledgePoint,
    Mastery,
    MasteryHistory,
    Mistake,
    Task,
    User,
)
from .experiments import build_ranking
from .knowledge_map import _mistake_counts
from .rules import MISTAKE_CATEGORIES, completion_rate

STRATEGY_LABELS = {
    "read": "精读理解",
    "practice": "刷题训练",
    "flashcard": "闪卡记忆",
    "ai_tutor": "AI 讲解",
}


def build_twin(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_map = {point.id: point for point in points}
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    mastery = {row.kp_id: row.value for row in rows}
    mistakes = _mistake_counts(db, user.id, goal.id)
    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id, KnowledgeGap.goal_id == goal.id
        )
    ).all()
    gap_by_kp = {gap.kp_id: gap.status for gap in gaps}

    matrix = [
        {
            "kp_id": point.id,
            "name": point.name,
            "parent": point_map.get(point.parent_id).name if point.parent_id else None,
            "weight": point.weight,
            "mastery": round(mastery.get(point.id, 0.0), 4),
            "mistake_count": mistakes.get(point.id, 0),
            "status": gap_by_kp.get(point.id, "normal"),
        }
        for point in points
    ]

    category_rows = db.scalars(
        select(Mistake).where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
    ).all()
    distribution: Dict[str, int] = defaultdict(int)
    for row in category_rows:
        distribution[row.category] += 1
    mistake_distribution = [
        {
            "category": key,
            "label": label,
            "count": distribution.get(key, 0),
        }
        for key, label in MISTAKE_CATEGORIES.items()
    ]

    trend = []
    for offset in range(7, -1, -1):
        week_end = today - timedelta(days=offset * 7)
        week_start = week_end - timedelta(days=6)
        tasks = db.scalars(
            select(Task).where(
                Task.user_id == user.id,
                Task.goal_id == goal.id,
                Task.day >= week_start,
                Task.day <= week_end,
            )
        ).all()
        judged = [task for task in tasks if task.status != "skipped"]
        done = [task for task in judged if task.status == "done"]
        trend.append(
            {
                "week_start": week_start,
                "done": len(done),
                "minutes": sum(task.duration_min for task in done),
                "completion_rate": completion_rate(len(done), len(judged)),
            }
        )

    ranking = build_ranking(db, user.id, goal.id)
    for item in ranking:
        item["label"] = STRATEGY_LABELS.get(item["strategy"], item["label"])

    return {
        "knowledge_matrix": matrix,
        "mistake_distribution": mistake_distribution,
        "behavior_trend": trend,
        "strategy_ranking": ranking,
    }

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_forecast(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> Dict:
    """规则型情景推演：基于当前掌握度、近 28 天完成率与复习阶段，给出 7/14/30 天区间。

    预测只作为可解释的初始基线，不伪造精确值；数据不足时降低置信度并标注。
    """
    today = today or date.today()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    current = round(sum(row.value for row in rows) / len(rows), 4) if rows else 0.0
    avg_stage = (
        round(sum(row.review_stage for row in rows) / len(rows), 2) if rows else 0.0
    )

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
    rate = completion_rate(len(done), len(judged))

    history_count = db.scalar(
        select(func.count(MasteryHistory.id)).where(
            MasteryHistory.user_id == user.id,
            MasteryHistory.kp_id.in_([point.id for point in points] or [0]),
        )
    ) or 0
    data_points = len(judged) + int(history_count)
    confidence = min(0.9, round(0.2 + data_points * 0.02, 2))
    insufficient = data_points < 5

    daily_gain = round(rate * 0.02, 4)
    decay = round(max(0.0, 0.006 - avg_stage * 0.001), 4)
    band = round((1 - rate) * 0.08 + 0.03, 4)

    assumptions = [
        "未来保持近 28 天的每日投入与完成率",
        "复习任务按 1/2/4/7/15 天间隔按时完成",
        "期间无长时间中断或重大状态变化",
    ]
    horizons = []
    for horizon in (7, 14, 30):
        projected = _clamp(current + (daily_gain - decay) * horizon)
        spread = band * min(horizon, 30) / 30
        horizons.append(
            {
                "horizon_days": horizon,
                "projected_mastery": round(projected, 4),
                "low": round(_clamp(projected - spread), 4),
                "high": round(_clamp(projected + spread), 4),
                "confidence": confidence,
                "assumptions": assumptions,
            }
        )

    if insufficient:
        uncertainty = "证据不足：当前学习事件与掌握快照较少，预测仅作方向参考。"
    elif rate < 0.5:
        uncertainty = "完成率偏低，预测不确定性较大，建议先恢复学习节奏。"
    else:
        uncertainty = "预测基于规则模型，展示的是区间而非单点承诺。"

    return {
        "horizons": horizons,
        "current_mastery": current,
        "method": "rule-decay-v1",
        "uncertainty": uncertainty,
        "data_points": data_points,
        "insufficient": insufficient,
    }