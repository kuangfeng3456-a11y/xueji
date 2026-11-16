"""收益密度排程预览（A3）：对比 v1 优先级与 v2 收益密度，展示先修门控影响。"""

from collections import defaultdict
from datetime import date
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    KnowledgeDependency,
    KnowledgePoint,
    LearningEvent,
    Mastery,
    User,
)
from .rules import (
    days_left,
    expected_gain,
    gate_for_prerequisites,
    mastery_uncertainty,
    retention,
    stability_for_stage,
    task_priority,
    value_density,
)


def schedule_preview(db: Session, user: User, goal, limit: int = 8, minutes: int = 20) -> Dict:
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    point_map = {point.id: point for point in points}
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids] or list(points)

    masteries = {
        row.kp_id: row
        for row in db.scalars(
            select(Mastery).where(
                Mastery.user_id == user.id,
                Mastery.kp_id.in_(list(point_map) or [0]),
            )
        ).all()
    }
    counts = dict(
        db.execute(
            select(LearningEvent.kp_id, func.count(LearningEvent.id))
            .where(
                LearningEvent.user_id == user.id,
                LearningEvent.goal_id == goal.id,
                LearningEvent.event_type == "answer",
            )
            .group_by(LearningEvent.kp_id)
        ).all()
    )
    reverse: Dict[int, List[int]] = defaultdict(list)
    for dep in db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal.id)
    ).all():
        reverse[dep.to_kp_id].append(dep.from_kp_id)

    today = date.today()
    remain = days_left(goal.exam_date, today)
    rows = []
    for point in leaves:
        record = masteries.get(point.id)
        mastery = record.value if record else 0.0
        stage = record.review_stage if record else 0
        stability = stability_for_stage(stage)
        last_day = record.updated_at.date() if record and record.updated_at else today
        retention_now = retention(max(0, (today - last_day).days), stability)
        n_eff = float(counts.get(point.id, 0))
        uncertainty = mastery_uncertainty(mastery, n_eff)
        prereq_values = [
            (masteries.get(pid).value if masteries.get(pid) else 0.0)
            for pid in reverse.get(point.id, [])
        ]
        gate = gate_for_prerequisites(prereq_values)
        density = value_density(
            point.weight, mastery, retention_now, uncertainty, remain, gate, minutes
        )
        rows.append(
            {
                "kp_id": point.id,
                "name": point.name,
                "weight": round(point.weight, 3),
                "mastery": round(mastery, 3),
                "retention": retention_now,
                "uncertainty": uncertainty,
                "gate": gate,
                "prereq_count": len(prereq_values),
                "v1_priority": task_priority(point.weight, mastery, remain),
                "v2_density": density["density"],
                "v2_value": density["value"],
                "expected_gain": expected_gain(point.weight, mastery, "practice", gate),
            }
        )

    v1 = sorted(rows, key=lambda item: item["v1_priority"], reverse=True)[:limit]
    v2 = sorted(rows, key=lambda item: item["v2_density"], reverse=True)[:limit]
    return {
        "remain_days": remain,
        "minutes": minutes,
        "v1_order": [item["kp_id"] for item in v1],
        "v2_order": [item["kp_id"] for item in v2],
        "v1": v1,
        "v2": v2,
        "params": {
            "lambda_forget": 0.6,
            "lambda_uncertainty": 0.3,
            "buffer_ratio": 0.15,
            "gate_threshold": 0.5,
            "eta_practice": 0.18,
        },
        "formula": "V = w·[(1-m)+0.6·(1-R)+0.3·u]·U(d)·G；ρ = V / 分钟；先修 m<0.5 时 G=0.5",
        "version": "rules-v2.0",
    }