"""家长授权与成长摘要：学生授权后才可查看，可随时撤销。"""

from datetime import date, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ConsentRecord,
    Goal,
    KnowledgePoint,
    Mastery,
    MasteryHistory,
    Task,
    User,
)
from .rules import completion_rate

SCOPE = "parent_report"


def get_consent(db: Session, user_id: int, scope: str = SCOPE) -> Optional[ConsentRecord]:
    return db.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id, ConsentRecord.scope == scope)
        .order_by(ConsentRecord.id.desc())
    )


def set_consent(db: Session, user_id: int, scope: str, granted: bool) -> ConsentRecord:
    record = get_consent(db, user_id, scope)
    now = datetime.utcnow()
    if record is None:
        record = ConsentRecord(user_id=user_id, scope=scope)
        db.add(record)
    record.granted = granted
    if granted:
        record.granted_at = now
        record.revoked_at = None
    else:
        record.revoked_at = now
    db.commit()
    db.refresh(record)
    return record


def consent_dict(record: Optional[ConsentRecord]) -> Dict:
    if record is None:
        return {
            "scope": SCOPE,
            "granted": False,
            "granted_at": None,
            "revoked_at": None,
        }
    return {
        "scope": record.scope,
        "granted": bool(record.granted),
        "granted_at": record.granted_at.isoformat() if record.granted_at else None,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
    }


def build_parent_report(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_ids = [point.id for point in points]
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id, Mastery.kp_id.in_(point_ids or [0])
        )
    ).all()
    current = round(sum(row.value for row in rows) / len(rows), 4) if rows else 0.0

    week_ago = today - timedelta(days=7)
    baseline = current
    history = db.scalars(
        select(MasteryHistory).where(
            MasteryHistory.user_id == user.id,
            MasteryHistory.kp_id.in_(point_ids or [0]),
        )
    ).all()
    early = [row.value for row in history if row.day <= week_ago]
    if early:
        baseline = round(sum(early) / len(early), 4)
    delta = round(current - baseline, 4)

    week_start = today - timedelta(days=6)
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day >= week_start,
            Task.day <= today,
        )
    ).all()
    judged = [task for task in tasks if task.status != "skipped"]
    done = [task for task in judged if task.status == "done"]
    rate = completion_rate(len(done), len(judged))

    if rate < 0.5:
        support = "本周完成率偏低，建议家长先帮助稳定作息，不额外加量。"
    elif delta > 0:
        support = "本周掌握度稳步提升，建议家长给予正向反馈并保持当前节奏。"
    else:
        support = "本周状态平稳，可与孩子一起确认下阶段目标与每日可用时间。"
    suggestions = [
        support,
        "关注过程而非单次分数，避免用排名施压。",
        "如需更多细节，请与孩子沟通后由其决定是否扩大授权范围。",
    ]

    return {
        "student": user.nickname or user.username,
        "goal": goal.exam_name,
        "days_left": max(0, (goal.exam_date - today).days),
        "avg_mastery": round(current * 100),
        "mastery_delta": round(delta * 100, 1),
        "completion_rate": round(rate * 100),
        "suggestions": suggestions,
        "scope_note": "仅展示经学生授权的成长摘要，不含私人对话与原始错题。",
        "generated_at": datetime.utcnow().isoformat(),
    }