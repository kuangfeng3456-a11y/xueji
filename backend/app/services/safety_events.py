"""安全事件记录（文档 9.3 / 附录 B）：只记类型与处置，不保存对话原文。"""

import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from ..models import SafetyEvent


def hash_user(user_id: Optional[int]) -> str:
    if not user_id:
        return ""
    return "u_" + hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def record_safety_event(
    db: Session,
    user_id: Optional[int],
    event_type: str = "injection",
    level: str = "medium",
    action: str = "flagged",
) -> SafetyEvent:
    event = SafetyEvent(
        user_hash=hash_user(user_id),
        type=event_type[:16],
        level=level[:16],
        action=action[:64],
    )
    db.add(event)
    db.flush()
    return event


def list_safety_events(db: Session, limit: int = 20):
    from sqlalchemy import select

    rows = db.scalars(select(SafetyEvent).order_by(SafetyEvent.id.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "type": row.type,
            "level": row.level,
            "action": row.action,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
