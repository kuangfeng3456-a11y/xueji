"""闪卡复习：把知识点变成可翻转卡片，用间隔重复驱动掌握度。"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, ReviewCard
from .advanced import phase_for
from .mastery_service import apply_answer
from .rules import days_left, days_to_target, retention, stability_for_stage, update_stability

TARGET_RETENTION = 0.90  # 强化期默认；有考试日期时改用阶段目标


def _phase_for_goal(db: Session, goal_id: int, today: date) -> dict:
    goal = db.get(Goal, goal_id)
    remain = days_left(goal.exam_date, today) if goal and goal.exam_date else 30
    return phase_for(remain)


def _goal_points(db: Session, goal_id: int) -> List[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids]
    return leaves or points


def build_deck(
    db: Session, user_id: int, goal_id: int, limit: int = 20, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    points = _goal_points(db, goal_id)
    phase = _phase_for_goal(db, goal_id, today)
    target = float(phase.get("target_retention") or TARGET_RETENTION)
    point_map = {point.id: point for point in points}
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    mastery_map = {row.kp_id: row for row in rows}
    card_rows = db.scalars(
        select(ReviewCard).where(
            ReviewCard.user_id == user_id,
            ReviewCard.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    review_map = {row.kp_id: row for row in card_rows}

    parent_names = {
        point.id: point.name
        for point in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    }

    cards = []
    for point in points:
        record = mastery_map.get(point.id)
        review = review_map.get(point.id)
        mastery = record.value if record else 0.0
        next_review = review.next_review if review and review.next_review else (
            record.next_review_at if record else None
        )
        due = next_review is None or next_review <= today
        if due:
            reason = "遗忘曲线到期"
        elif mastery < 0.35:
            reason = "掌握度偏低，优先补基础"
        elif mastery < 0.7:
            reason = "待巩固"
        else:
            reason = "保持手感"
        stability = (
            review.stability
            if review and review.stability
            else stability_for_stage(record.review_stage if record else 0)
        )
        reference_time = (
            review.last_review
            if review and review.last_review
            else (record.updated_at if record and record.updated_at else datetime.utcnow())
        )
        last_day = reference_time.date()
        retention_now = retention(max(0, (today - last_day).days), stability)
        cards.append(
            {
                "kp_id": point.id,
                "kp_name": point.name,
                "parent": parent_names.get(point.parent_id) if point.parent_id else None,
                "weight": point.weight,
                "mastery": round(mastery, 4),
                "next_review_at": next_review,
                "due": due,
                "reason": reason,
                "retention_now": retention_now,
                "stability_days": round(stability, 2),
                "lapses": review.lapses if review else 0,
                "reps": review.reps if review else 0,
                "days_to_target": days_to_target(target, stability),
                "target_retention": target,
                "phase": phase["phase"],
                "phase_label": phase["label"],
            }
        )
    cards.sort(key=lambda item: (not item["due"], item["mastery"], -item["weight"]))
    due_count = len([item for item in cards if item["due"]])
    return {
        "cards": cards[:limit],
        "total": len(cards),
        "due_count": due_count,
        "target_retention": target,
        "phase": phase["phase"],
        "phase_label": phase["label"],
    }


def review_card(
    db: Session, user_id: int, goal_id: int, kp_id: int, remembered: bool
) -> Dict:
    point = db.get(KnowledgePoint, kp_id)
    if not point or point.goal_id != goal_id:
        raise ValueError("知识点不存在")
    record = apply_answer(db, user_id, point, correct=remembered)

    # 文档 5.2：review_cards 维护记忆稳定度 S、遗忘次数与下次复习日
    today = date.today()
    card = db.scalar(
        select(ReviewCard).where(
            ReviewCard.user_id == user_id, ReviewCard.kp_id == point.id
        )
    )
    if card is None:
        card = ReviewCard(user_id=user_id, goal_id=goal_id, kp_id=point.id, stability=1.0)
        db.add(card)
        db.flush()
    base_stability = float(card.stability or 1.0)
    reference = card.last_review or record.updated_at or datetime.utcnow()
    elapsed = max(0, (datetime.utcnow() - reference).days)
    retention_now = retention(elapsed, base_stability)
    card.stability = update_stability(base_stability, retention_now, remembered)
    card.reps = int(card.reps or 0) + 1
    card.lapses = int(card.lapses or 0) + (0 if remembered else 1)
    card.difficulty = round(min(1.0, max(0.0, 1.0 - record.value)), 3)
    card.last_review = datetime.utcnow()
    phase = _phase_for_goal(db, goal_id, today)
    target = float(phase.get("target_retention") or TARGET_RETENTION)
    card.next_review = today + timedelta(
        days=max(1, days_to_target(target, card.stability))
    )
    db.commit()

    deck = build_deck(db, user_id, goal_id)
    return {
        "kp_id": point.id,
        "mastery": record.value,
        "next_review_at": card.next_review,
        "stability_days": round(card.stability, 2),
        "lapses": card.lapses,
        "retention_now": retention_now,
        "stage": record.review_stage,
        "remaining_due": deck["due_count"],
        "target_retention": target,
        "phase": phase["phase"],
        "phase_label": phase["label"],
    }
