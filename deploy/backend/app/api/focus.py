import uuid
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import FocusSession, Goal, Task, User, Violation
from ..services.learning_events import record_event
from ..schemas import (
    FocusAbortIn,
    FocusFinishIn,
    FocusHeartbeatIn,
    FocusSessionOut,
    FocusStartIn,
    ViolationOut,
)

router = APIRouter(tags=["强制学习与摄像头"])

MAX_LEAVES = 3
PASS_RATIO = 0.6


def _record_violation(db: Session, user_id: int, goal_id: int, kind: str, detail: str) -> None:
    db.add(
        Violation(
            user_id=user_id,
            goal_id=goal_id,
            day=date.today(),
            kind=kind,
            detail=detail,
        )
    )


def _remaining_seconds(session: FocusSession) -> int:
    if session.status != "active":
        return 0
    elapsed = (datetime.utcnow() - session.started_at).total_seconds()
    return max(int(session.planned_minutes * 60 - elapsed), 0)


def _today_tasks(db: Session, user_id: int, goal_id: int) -> List[Task]:
    return db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal_id,
            Task.day == date.today(),
        )
    ).all()


def _session_out(db: Session, session: FocusSession) -> FocusSessionOut:
    task = db.get(Task, session.task_id) if session.task_id else None
    today_tasks = _today_tasks(db, session.user_id, session.goal_id)
    unfinished = [task for task in today_tasks if task.status == "pending"]
    return FocusSessionOut(
        id=session.id,
        goal_id=session.goal_id,
        task_id=session.task_id,
        task_title=task.title if task else None,
        planned_minutes=session.planned_minutes,
        actual_minutes=session.actual_minutes,
        camera_enabled=session.camera_enabled,
        status=session.status,
        leaves=session.leaves,
        snapshots=session.snapshots,
        note=session.note,
        started_at=session.started_at,
        ended_at=session.ended_at,
        remaining_seconds=_remaining_seconds(session),
        unlocked=bool(today_tasks) and not unfinished,
    )


def _get_session(db: Session, session_id: int, user: User) -> FocusSession:
    session = db.get(FocusSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="专注记录不存在")
    return session


@router.post("/focus/start", response_model=FocusSessionOut)
def start_focus(
    payload: FocusStartIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FocusSessionOut:
    goal = get_user_goal(payload.goal_id, user, db)

    active = db.scalar(
        select(FocusSession).where(
            FocusSession.user_id == user.id,
            FocusSession.goal_id == goal.id,
            FocusSession.status == "active",
        )
    )
    if active:
        return _session_out(db, active)

    if payload.task_id is not None:
        task = db.get(Task, payload.task_id)
        if not task or task.user_id != user.id or task.goal_id != goal.id:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.status == "done":
            raise HTTPException(status_code=400, detail="该任务已经完成")

    session = FocusSession(
        user_id=user.id,
        goal_id=goal.id,
        task_id=payload.task_id,
        planned_minutes=payload.planned_minutes,
        camera_enabled=bool(payload.camera_enabled or goal.camera_required),
        status="active",
        started_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.get("/focus/active", response_model=Optional[FocusSessionOut])
def active_focus(
    goal_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Optional[FocusSessionOut]:
    query = select(FocusSession).where(
        FocusSession.user_id == user.id, FocusSession.status == "active"
    )
    if goal_id is not None:
        query = query.where(FocusSession.goal_id == goal_id)
    session = db.scalar(query.order_by(FocusSession.started_at.desc()))

    if session and _remaining_seconds(session) == 0 and session.planned_minutes > 0:
        session.status = "completed"
        session.actual_minutes = session.planned_minutes
        session.ended_at = datetime.utcnow()
        task = db.get(Task, session.task_id) if session.task_id else None
        if task and task.status != "done":
            task.status = "done"
            task.done_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
    return _session_out(db, session) if session else None


@router.post("/focus/{session_id}/heartbeat", response_model=FocusSessionOut)
def heartbeat(
    session_id: int,
    payload: FocusHeartbeatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FocusSessionOut:
    session = _get_session(db, session_id, user)
    if session.status != "active":
        return _session_out(db, session)

    session.leaves = max(session.leaves, payload.leaves)
    if session.leaves >= MAX_LEAVES:
        session.status = "aborted"
        session.ended_at = datetime.utcnow()
        session.note = f"离开专注页面 {session.leaves} 次，自动中止"
        _record_violation(db, user.id, session.goal_id, "leave", session.note)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.post("/focus/{session_id}/snapshot")
async def upload_snapshot(
    session_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    session = _get_session(db, session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=400, detail="专注已结束，无法上传学习见证")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="图片超过 5MB")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="仅支持 jpg / png / webp")
    signatures = {
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".webp": (b"RIFF",),
    }
    if not any(data.startswith(signature) for signature in signatures[suffix]):
        raise HTTPException(status_code=400, detail="图片内容与扩展名不匹配")
    folder = Path(settings.UPLOAD_DIR) / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"focus_{session.id}_{uuid.uuid4().hex[:8]}{suffix}"
    (folder / filename).write_bytes(data)
    session.snapshots += 1
    db.commit()
    return {
        "url": f"/uploads/{user.id}/{filename}",
        "snapshots": session.snapshots,
    }


class FocusPresenceIn(BaseModel):
    present: bool = True
    luma: float = 0.0
    diff: float = 0.0
    note: str = Field(default="", max_length=120)


@router.post("/focus/{session_id}/presence")
def record_presence(
    session_id: int,
    payload: FocusPresenceIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """端侧在场判断的结果落库（文档 9.2 / E1）：只记结果，不接收原图。"""
    session = _get_session(db, session_id, user)
    if session.status != "active":
        return {"recorded": False, "reason": "专注已结束", "leaves": session.leaves, "snapshots": session.snapshots}
    session.snapshots = int(session.snapshots or 0) + 1
    if not payload.present:
        session.leaves = int(session.leaves or 0) + 1
    session.note = (payload.note or ("端侧判断：在场" if payload.present else "端侧判断：可能离开"))[:255]
    record_event(
        db,
        user.id,
        session.goal_id,
        "focus_presence",
        payload={"present": payload.present, "luma": payload.luma, "diff": payload.diff, "session_id": session.id},
    )
    db.commit()
    db.refresh(session)
    return {
        "recorded": True,
        "present": payload.present,
        "leaves": session.leaves,
        "snapshots": session.snapshots,
        "aborted": session.status != "active",
    }


@router.post("/focus/{session_id}/finish", response_model=FocusSessionOut)
def finish_focus(
    session_id: int,
    payload: FocusFinishIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FocusSessionOut:
    session = _get_session(db, session_id, user)
    if session.status != "active":
        return _session_out(db, session)

    elapsed = int((datetime.utcnow() - session.started_at).total_seconds() / 60)
    actual = payload.actual_minutes if payload.actual_minutes is not None else max(elapsed, 1)
    session.actual_minutes = min(actual, 600)
    session.ended_at = datetime.utcnow()
    session.note = payload.note

    if session.actual_minutes < session.planned_minutes * PASS_RATIO:
        session.status = "aborted"
        _record_violation(
            db,
            user.id,
            session.goal_id,
            "short",
            f"计划专注 {session.planned_minutes} 分钟，实际只完成 {session.actual_minutes} 分钟",
        )
    else:
        session.status = "completed"
        if session.task_id:
            task = db.get(Task, session.task_id)
            if task and task.status != "done":
                task.status = "done"
                task.done_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.post("/focus/{session_id}/abort", response_model=FocusSessionOut)
def abort_focus(
    session_id: int,
    payload: FocusAbortIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FocusSessionOut:
    session = _get_session(db, session_id, user)
    if session.status != "active":
        return _session_out(db, session)
    session.status = "aborted"
    session.ended_at = datetime.utcnow()
    session.note = payload.reason
    session.actual_minutes = max(
        int((datetime.utcnow() - session.started_at).total_seconds() / 60), 0
    )
    _record_violation(db, user.id, session.goal_id, "abort", payload.reason)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.get("/goals/{goal_id}/focus/summary")
def focus_summary(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """专注统计的全量口径（历史列表默认只返回最近 10 条，不能用于求和）。"""
    get_user_goal(goal_id, user, db)
    cond = (FocusSession.user_id == user.id, FocusSession.goal_id == goal_id)
    rows = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(FocusSession.actual_minutes), 0),
            func.coalesce(func.sum(case((FocusSession.status == "aborted", 1), else_=0)), 0),
            func.coalesce(func.sum(FocusSession.leaves), 0),
        ).where(*cond)
    ).one()
    sessions, total_minutes, aborted, leaves = rows
    today = date.today()
    today_minutes = db.scalar(
        select(func.coalesce(func.sum(FocusSession.actual_minutes), 0)).where(
            *cond, func.date(FocusSession.started_at) == today
        )
    )
    violations = db.scalar(
        select(func.count())
        .select_from(Violation)
        .where(Violation.user_id == user.id, Violation.goal_id == goal_id)
    )
    return {
        "violations": int(violations or 0),
        "sessions": int(sessions or 0),
        "total_minutes": int(total_minutes or 0),
        "today_minutes": int(today_minutes or 0),
        "aborted": int(aborted or 0),
        "leaves": int(leaves or 0),
        "avg_minutes": round(float(total_minutes or 0) / sessions, 1) if sessions else 0.0,
    }


@router.get("/goals/{goal_id}/violations", response_model=List[ViolationOut])
def list_violations(
    goal_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[ViolationOut]:
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(Violation)
        .where(Violation.user_id == user.id, Violation.goal_id == goal.id)
        .order_by(Violation.created_at.desc())
        .limit(limit)
    ).all()
    return [ViolationOut.model_validate(row) for row in rows]


@router.get("/focus/history", response_model=List[FocusSessionOut])
def focus_history(
    goal_id: int = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[FocusSessionOut]:
    get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(FocusSession)
        .where(FocusSession.user_id == user.id, FocusSession.goal_id == goal_id)
        .order_by(FocusSession.started_at.desc())
        .limit(limit)
    ).all()
    return [_session_out(db, row) for row in rows]