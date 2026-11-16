"""多轮语音教练：会话、历史与追问。"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CoachMessage, CoachSession, Goal, User
from .qa import answer_with_history


def _message_out(row: CoachMessage) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "text": row.text,
        "source": row.source,
        "created_at": row.created_at.isoformat(timespec="seconds"),
    }


def _session_out(row: CoachSession, messages: Optional[List[CoachMessage]] = None) -> dict:
    payload = {
        "id": row.id,
        "goal_id": row.goal_id,
        "title": row.title,
        "created_at": row.created_at.isoformat(timespec="seconds"),
        "updated_at": row.updated_at.isoformat(timespec="seconds"),
    }
    if messages is not None:
        payload["messages"] = [_message_out(item) for item in messages]
    return payload


def list_sessions(db: Session, user_id: int) -> List[dict]:
    rows = db.scalars(
        select(CoachSession)
        .where(CoachSession.user_id == user_id)
        .order_by(CoachSession.updated_at.desc(), CoachSession.id.desc())
    ).all()
    return [_session_out(row) for row in rows]


def get_session(db: Session, user: User, session_id: int) -> CoachSession:
    row = db.get(CoachSession, session_id)
    if row is None or row.user_id != user.id:
        raise ValueError("会话不存在")
    return row


def messages_of(db: Session, session_id: int, limit: int = 100) -> List[CoachMessage]:
    rows = db.scalars(
        select(CoachMessage)
        .where(CoachMessage.session_id == session_id)
        .order_by(CoachMessage.id.asc())
    ).all()
    if len(rows) > limit:
        return rows[-limit:]
    return rows


def open_session(db: Session, user: User, goal: Optional[Goal], title: str = "") -> dict:
    now = datetime.utcnow()
    row = CoachSession(
        user_id=user.id,
        goal_id=goal.id if goal else None,
        title=(title or "语音教练").strip()[:128] or "语音教练",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _session_out(row, [])


async def append_turn(
    db: Session,
    user: User,
    session: CoachSession,
    goal: Optional[Goal],
    text: str,
    source: str = "text",
) -> dict:
    content = (text or "").strip()
    if not content:
        raise ValueError("请先说点什么")
    if goal is not None and session.goal_id != goal.id:
        session.goal_id = goal.id
    history = [
        {"role": item.role, "text": item.text}
        for item in messages_of(db, session.id, limit=12)
    ]
    user_row = CoachMessage(session_id=session.id, role="user", text=content[:500], source=source)
    db.add(user_row)
    db.flush()
    result = await answer_with_history(db, user, goal, content, history)
    coach_row = CoachMessage(
        session_id=session.id,
        role="coach",
        text=result["answer"],
        source=result["source"],
    )
    db.add(coach_row)
    if session.title in ("", "语音教练") and source != "system":
        session.title = content[:40]
    session.updated_at = datetime.utcnow()
    db.commit()
    stored = messages_of(db, session.id)
    return {
        "session_id": session.id,
        "answer": result["answer"],
        "source": result["source"],
        "suggestions": result["suggestions"],
        "followup": result["followup"],
        "messages": [_message_out(item) for item in stored],
    }


def history_for(db: Session, user_id: int, session_id: Optional[int]) -> List[dict]:
    if not session_id:
        return []
    row = db.get(CoachSession, session_id)
    if row is None or row.user_id != user_id:
        return []
    return [{"role": item.role, "text": item.text} for item in messages_of(db, row.id, limit=8)]
