"""知识依赖图与潜在漏洞诊断。"""

from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Goal,
    KnowledgeDependency,
    KnowledgeGap,
    KnowledgePoint,
    Mastery,
    Mistake,
    User,
)


def ensure_dependencies(db: Session, goal: Goal) -> None:
    existing = db.scalar(
        select(KnowledgeDependency.id).where(KnowledgeDependency.goal_id == goal.id).limit(1)
    )
    if existing:
        return
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    if not points:
        return
    edges = []
    for point in points:
        if point.parent_id:
            edges.append((point.parent_id, point.id, "tree"))
    by_parent: Dict[int, List[KnowledgePoint]] = defaultdict(list)
    for point in points:
        if point.parent_id:
            by_parent[point.parent_id].append(point)
    for children in by_parent.values():
        children.sort(key=lambda item: item.id)
        for previous, current in zip(children, children[1:]):
            edges.append((previous.id, current.id, "sequence"))
    seen = set()
    for source, target, kind in edges:
        if (source, target) in seen:
            continue
        seen.add((source, target))
        db.add(
            KnowledgeDependency(
                goal_id=goal.id, from_kp_id=source, to_kp_id=target, source=kind
            )
        )
    db.commit()


def _mastery_map(db: Session, user_id: int, goal_id: int) -> Dict[int, float]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    return {row.kp_id: row.value for row in rows}


def _mistake_counts(db: Session, user_id: int, goal_id: int) -> Dict[int, int]:
    rows = db.execute(
        select(Mistake.kp_id, func.count(Mistake.id))
        .where(Mistake.user_id == user_id, Mistake.goal_id == goal_id)
        .group_by(Mistake.kp_id)
    ).all()
    return {kp_id: count for kp_id, count in rows if kp_id}


def prerequisites(db: Session, goal_id: int, kp_id: int, depth: int = 4) -> List[int]:
    edges = db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal_id)
    ).all()
    reverse: Dict[int, List[int]] = defaultdict(list)
    for edge in edges:
        reverse[edge.to_kp_id].append(edge.from_kp_id)
    result: List[int] = []
    frontier = [kp_id]
    for _ in range(depth):
        next_frontier = []
        for node in frontier:
            for parent in reverse.get(node, []):
                if parent not in result:
                    result.append(parent)
                    next_frontier.append(parent)
        if not next_frontier:
            break
        frontier = next_frontier
    return result


def refresh_candidates(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> List[KnowledgeGap]:
    today = today or date.today()
    ensure_dependencies(db, goal)
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids] or points
    mastery = _mastery_map(db, user.id, goal.id)
    mistakes = _mistake_counts(db, user.id, goal.id)

    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id, KnowledgeGap.goal_id == goal.id
        )
    ).all()
    known = {gap.kp_id for gap in gaps}
    created = []
    for point in leaves:
        if point.id in known:
            continue
        value = mastery.get(point.id, 0.0)
        mistake_count = mistakes.get(point.id, 0)
        weak_prereq = any(
            mastery.get(pid, 0.0) < max(0.45, value - 0.15)
            for pid in prerequisites(db, goal.id, point.id)
        )
        trigger = (
            (mistake_count >= 2 and value < 0.6)
            or (point.weight >= 1.5 and value < 0.35)
            or (weak_prereq and value < 0.5)
        )
        if not trigger:
            continue
        evidence = f"掌握度 {round(value * 100)}%，错题 {mistake_count} 道"
        if weak_prereq:
            evidence += "，先修链中存在更薄弱环节"
        gap = KnowledgeGap(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            status="candidate",
            evidence=evidence,
            source="rule",
        )
        db.add(gap)
        created.append(gap)
    db.commit()
    return db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id,
            KnowledgeGap.goal_id == goal.id,
            KnowledgeGap.status == "candidate",
        )
    ).all()


def build_graph(db: Session, user: User, goal: Goal, today: Optional[date] = None) -> Dict:
    today = today or date.today()
    refresh_candidates(db, user, goal, today)
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_map = {point.id: point for point in points}
    mastery = _mastery_map(db, user.id, goal.id)
    mistakes = _mistake_counts(db, user.id, goal.id)
    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id, KnowledgeGap.goal_id == goal.id
        )
    ).all()
    gap_by_kp = {gap.kp_id: gap for gap in gaps}

    nodes = []
    for point in points:
        gap = gap_by_kp.get(point.id)
        nodes.append(
            {
                "kp_id": point.id,
                "name": point.name,
                "parent": point_map.get(point.parent_id).name if point.parent_id else None,
                "weight": point.weight,
                "mastery": round(mastery.get(point.id, 0.0), 4),
                "status": gap.status if gap else "normal",
                "mistake_count": mistakes.get(point.id, 0),
            }
        )
    edges = [
        {"source": edge.from_kp_id, "target": edge.to_kp_id, "kind": edge.source}
        for edge in db.scalars(
            select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal.id)
        ).all()
    ]
    candidates = [
        {
            "id": gap.id,
            "kp_id": gap.kp_id,
            "kp_name": point_map.get(gap.kp_id).name if gap.kp_id in point_map else "",
            "status": gap.status,
            "evidence": gap.evidence,
            "source": gap.source,
        }
        for gap in gaps
        if gap.status == "candidate"
    ]
    verified = [
        {
            "id": gap.id,
            "kp_id": gap.kp_id,
            "kp_name": point_map.get(gap.kp_id).name if gap.kp_id in point_map else "",
            "status": gap.status,
            "evidence": gap.evidence,
            "source": gap.source,
        }
        for gap in gaps
        if gap.status == "verified"
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "candidates": candidates,
        "verified": verified,
        "fixed_count": len([gap for gap in gaps if gap.status == "fixed"]),
    }