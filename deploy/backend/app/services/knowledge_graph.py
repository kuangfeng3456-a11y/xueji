"""显式知识图谱：节点、先修/易混淆关系、统计与邻居查询。"""

from collections import defaultdict
from typing import Dict, List

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..models import (
    KnowledgeDependency,
    KnowledgeEdge,
    KnowledgePoint,
    Mastery,
    User,
)

RELATION_LABELS = {
    "prerequisite": "先修",
    "confusable": "易混淆",
    "related": "相关",
}
MAX_GROUP = 6


def _level(value: float) -> str:
    if value >= 0.8:
        return "excellent"
    if value >= 0.6:
        return "good"
    if value >= 0.4:
        return "risk"
    return "critical"


def sync_edges(db: Session, goal_id: int) -> Dict:
    db.execute(delete(KnowledgeEdge).where(KnowledgeEdge.goal_id == goal_id))
    db.flush()

    prerequisites = 0
    for dep in db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal_id)
    ).all():
        db.add(
            KnowledgeEdge(
                goal_id=goal_id,
                from_kp_id=dep.from_kp_id,
                to_kp_id=dep.to_kp_id,
                relation_type="prerequisite",
                weight=1.0,
            )
        )
        prerequisites += 1

    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)
    ).all()
    groups: Dict[int, List[KnowledgePoint]] = defaultdict(list)
    for point in points:
        if point.parent_id:
            groups[point.parent_id].append(point)

    confusable = 0
    for siblings in groups.values():
        ordered = sorted(siblings, key=lambda item: (item.weight, item.name))[:MAX_GROUP]
        for index in range(len(ordered) - 1):
            first, second = ordered[index], ordered[index + 1]
            db.add(
                KnowledgeEdge(
                    goal_id=goal_id,
                    from_kp_id=first.id,
                    to_kp_id=second.id,
                    relation_type="confusable",
                    weight=0.6,
                )
            )
            confusable += 1

    db.commit()
    return {
        "prerequisites": prerequisites,
        "confusable": confusable,
        "edges": prerequisites + confusable,
    }


def _ensure(db: Session, goal_id: int) -> None:
    exists = db.scalar(
        select(KnowledgeEdge.id).where(KnowledgeEdge.goal_id == goal_id).limit(1)
    )
    if exists is None:
        sync_edges(db, goal_id)


def get_graph(db: Session, user: User, goal) -> Dict:
    _ensure(db, goal.id)
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    point_map = {point.id: point for point in points}
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id, Mastery.kp_id.in_(list(point_map) or [0])
        )
    ).all()
    mastery = {row.kp_id: row.value for row in rows}

    nodes = []
    for point in points:
        value = mastery.get(point.id, 0.0)
        parent = point_map.get(point.parent_id) if point.parent_id else None
        nodes.append(
            {
                "id": point.id,
                "name": point.name,
                "parent": parent.name if parent else None,
                "weight": round(point.weight, 2),
                "mastery": round(value, 3),
                "level": _level(value),
            }
        )

    edges = []
    for edge in db.scalars(
        select(KnowledgeEdge).where(KnowledgeEdge.goal_id == goal.id)
    ).all():
        source = point_map.get(edge.from_kp_id)
        target = point_map.get(edge.to_kp_id)
        if source is None or target is None:
            continue
        edges.append(
            {
                "id": edge.id,
                "from": edge.from_kp_id,
                "to": edge.to_kp_id,
                "from_name": source.name,
                "to_name": target.name,
                "type": edge.relation_type,
                "label": RELATION_LABELS.get(edge.relation_type, edge.relation_type),
                "weight": edge.weight,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "prerequisite": len([item for item in edges if item["type"] == "prerequisite"]),
            "confusable": len([item for item in edges if item["type"] == "confusable"]),
        },
        "relations": RELATION_LABELS,
    }


def node_detail(db: Session, user: User, goal, kp_id: int) -> Dict:
    _ensure(db, goal.id)
    point = db.get(KnowledgePoint, kp_id)
    if point is None or point.goal_id != goal.id:
        raise ValueError("知识点不存在")

    mastery = db.scalar(
        select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == kp_id)
    )
    value = mastery.value if mastery else 0.0

    rows = db.scalars(
        select(KnowledgeEdge).where(
            KnowledgeEdge.goal_id == goal.id,
            or_(
                KnowledgeEdge.from_kp_id == kp_id,
                KnowledgeEdge.to_kp_id == kp_id,
            ),
        )
    ).all()
    point_map = {
        item.id: item
        for item in db.scalars(
            select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
        ).all()
    }
    neighbors = []
    for edge in rows:
        other_id = edge.to_kp_id if edge.from_kp_id == kp_id else edge.from_kp_id
        other = point_map.get(other_id)
        if other is None:
            continue
        neighbors.append(
            {
                "kp_id": other.id,
                "name": other.name,
                "type": edge.relation_type,
                "label": RELATION_LABELS.get(edge.relation_type, edge.relation_type),
                "direction": "out" if edge.from_kp_id == kp_id else "in",
            }
        )

    return {
        "kp_id": point.id,
        "name": point.name,
        "parent": point_map.get(point.parent_id).name if point.parent_id and point.parent_id in point_map else None,
        "weight": round(point.weight, 2),
        "mastery": round(value, 3),
        "level": _level(value),
        "neighbors": neighbors,
    }