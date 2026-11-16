from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import KnowledgePoint, LearningEvent, Mastery, MasteryHistory
from .learning_events import record_event
from .rules import (
    bkt_update,
    mastery_confidence,
    mastery_uncertainty,
    next_review_date,
    update_mastery,
)


def get_mastery(db: Session, user_id: int, kp_id: int) -> Optional[Mastery]:
    return db.scalar(select(Mastery).where(Mastery.user_id == user_id, Mastery.kp_id == kp_id))


def ensure_mastery(db: Session, user_id: int, kp: KnowledgePoint) -> Mastery:
    record = get_mastery(db, user_id, kp.id)
    if record is None:
        record = Mastery(user_id=user_id, kp_id=kp.id, value=0.0, review_stage=0, next_review_at=None)
        db.add(record)
        db.flush()
    return record


def ensure_goal_mastery(db: Session, user_id: int, goal_id: int) -> None:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    for point in points:
        ensure_mastery(db, user_id, point)
    db.flush()


def record_history(db: Session, user_id: int, kp_id: int, value: float, day: Optional[date] = None) -> None:
    day = day or date.today()
    row = db.scalar(
        select(MasteryHistory).where(
            MasteryHistory.user_id == user_id,
            MasteryHistory.kp_id == kp_id,
            MasteryHistory.day == day,
        )
    )
    if row is None:
        db.add(MasteryHistory(user_id=user_id, kp_id=kp_id, day=day, value=round(value, 4)))
    else:
        row.value = round(value, 4)


def apply_answer(
    db: Session,
    user_id: int,
    kp: KnowledgePoint,
    correct: bool,
    day: Optional[date] = None,
    question_type: str = "choice",
    evidence_weight: float = 1.0,
) -> Mastery:
    day = day or date.today()
    record = ensure_mastery(db, user_id, kp)
    record.value = bkt_update(record.value, correct, question_type, evidence_weight)
    record.next_review_at, record.review_stage = next_review_date(correct, record.review_stage, day)
    from datetime import datetime

    evidence_count = db.scalar(
        select(func.count(LearningEvent.id)).where(
            LearningEvent.user_id == user_id,
            LearningEvent.kp_id == kp.id,
            LearningEvent.event_type == "answer",
        )
    ) or 0
    n_eff = round(evidence_count + max(evidence_weight, 0.0), 2)
    confidence = mastery_confidence(n_eff)
    uncertainty = mastery_uncertainty(record.value, n_eff)

    record.updated_at = datetime.utcnow()
    record_history(db, user_id, kp.id, record.value, day)
    record_event(
        db,
        user_id,
        kp.goal_id,
        "answer",
        kp.id,
        {
            "correct": correct,
            "mastery_after": round(record.value, 4),
            "review_stage": record.review_stage,
            "confidence": confidence,
            "uncertainty": uncertainty,
            "n_eff": n_eff,
            "question_type": question_type,
            "evidence_weight": evidence_weight,
            "engine": "rules-v2.0",
        },
    )
    db.flush()
    return record


def touch_history_for_today(db: Session, user_id: int, goal_id: int, day: Optional[date] = None) -> None:
    """确保今天有一次掌握度快照，供周报计算变化。"""
    day = day or date.today()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    for point in points:
        record = ensure_mastery(db, user_id, point)
        record_history(db, user_id, point.id, record.value, day)
    db.flush()