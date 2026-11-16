from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Goal, User
from ..schemas import AskIn, AskOut
from ..services import cloud_services as cs
from ..services.coach_memory import (
    _session_out,
    append_turn,
    get_session,
    list_sessions,
    messages_of,
    open_session,
)
from ..services.practice_loop import close_coaching
from ..services.qa import answer_question

router = APIRouter(prefix="/coach", tags=["语音问答"])


class SessionIn(BaseModel):
    goal_id: Optional[int] = None
    title: str = Field(default="", max_length=128)


class SessionMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    goal_id: Optional[int] = None


def _goal_for(db: Session, user: User, goal_id: Optional[int]) -> Optional[Goal]:
    if goal_id is not None:
        return get_user_goal(goal_id, user, db)
    return db.scalar(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc()).limit(1))


@router.post("/ask", response_model=AskOut)
async def ask(
    payload: AskIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AskOut:
    goal: Optional[Goal] = None
    if payload.goal_id is not None:
        goal = db.get(Goal, payload.goal_id)
        if goal and goal.user_id != user.id:
            goal = None
    if goal is None:
        goal = db.scalar(
            select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc()).limit(1)
        )
    result = await answer_question(db, user, goal, payload.question)
    return AskOut(**result)


@router.post("/sessions", status_code=201)
def create_session(
    payload: SessionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = _goal_for(db, user, payload.goal_id) if payload.goal_id else None
    return open_session(db, user, goal, payload.title)


@router.get("/sessions")
def sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"items": list_sessions(db, user.id)}


@router.get("/sessions/{session_id}")
def session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = get_session(db, user, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _session_out(row, messages_of(db, row.id))


@router.post("/sessions/{session_id}/messages")
async def session_message(
    session_id: int,
    payload: SessionMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = get_session(db, user, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    goal = _goal_for(db, user, payload.goal_id if payload.goal_id is not None else row.goal_id)
    try:
        return await append_turn(db, user, row, goal, payload.text, source="text")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sessions/{session_id}/close")
def close_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = get_session(db, user, session_id)
        return close_coaching(db, user, row)
    except ValueError as exc:
        status = 404 if "会话" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


@router.post("/sessions/{session_id}/voice")
async def session_voice(
    session_id: int,
    file: UploadFile = File(...),
    goal_id: Optional[int] = Form(default=None),
    audio_format: str = Form("wav"),
    sample_rate: int = Form(16000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """语音进：先识别再进入多轮会话。云端不可用时不编造文本，交由客户端改用本机识别或文字。"""
    try:
        row = get_session(db, user, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        return {
            "status": "error",
            "detail": "音频超过 8MB 上限，未调用云服务",
            "text": "",
            "fallback": "device_or_text",
            "fallback_label": "请缩短录音，或改用文字输入",
            "session_id": row.id,
        }
    heard = cs.sis_audio_to_text(raw, audio_format=audio_format or "wav", sample_rate=sample_rate or 16000)
    if heard.get("status") != cs.OK or not (heard.get("text") or "").strip():
        heard["text"] = heard.get("text") or ""
        heard["fallback"] = "device_or_text"
        heard["fallback_label"] = "云端语音识别不可用，请改用本机语音或文字输入"
        heard["session_id"] = row.id
        return heard
    goal = _goal_for(db, user, goal_id if goal_id is not None else row.goal_id)
    reply = await append_turn(db, user, row, goal, heard["text"], source="voice")
    reply["status"] = cs.OK
    reply["transcript"] = heard["text"]
    reply["fallback"] = ""
    reply["fallback_label"] = "云端语音识别"
    return reply