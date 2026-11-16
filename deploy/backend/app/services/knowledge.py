from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint
from .mastery_service import ensure_mastery


def persist_points(db: Session, user_id: int, goal: Goal, points: List[dict]) -> List[dict]:
    """把 [{name, parent, weight}] 写入知识点树，自动去重并初始化掌握度。"""
    existing = {
        point.name.lower(): point
        for point in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    }
    created: List[dict] = []
    for item in points:
        name = str(item.get("name", "")).strip()
        if not name or name.lower() in existing:
            continue
        parent_id = None
        parent_name = item.get("parent")
        if parent_name and str(parent_name).lower() in existing:
            parent_id = existing[str(parent_name).lower()].id
        try:
            weight = float(item.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        point = KnowledgePoint(
            goal_id=goal.id,
            name=name[:128],
            parent_id=parent_id,
            weight=max(0.1, min(weight, 5.0)),
        )
        db.add(point)
        db.flush()
        ensure_mastery(db, user_id, point)
        existing[name.lower()] = point
        created.append(
            {
                "id": point.id,
                "name": point.name,
                "parent_id": point.parent_id,
                "weight": point.weight,
            }
        )
    return created