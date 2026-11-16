"""统一学习事件流与掌握度明细接口。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services import learning_events

router = APIRouter(tags=["学习事件与掌握度"])


@router.get("/goals/{goal_id}/learning-events")
def list_learning_events(
    goal_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return {
        "events": learning_events.list_events(
            db, user.id, goal.id, limit=limit, event_type=event_type
        )
    }


@router.get("/goals/{goal_id}/learning-events/stats")
def learning_event_stats(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return learning_events.event_stats(db, user.id, goal.id)


@router.get("/goals/{goal_id}/mastery/{kp_id}/detail")
def mastery_detail(
    goal_id: int,
    kp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_user_goal(goal_id, user, db)
    try:
        return learning_events.mastery_detail(db, user.id, kp_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
@router.get("/events/recent")
def recent_events(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """事件总线的最近路由记录（文档 7.5）。"""
    from ..services.event_bus import recent_events as _recent

    rows = _recent(db, user_id=user.id, limit=limit)
    return {"total": len(rows), "items": rows}


@router.get("/events/routes")
def event_routes(user: User = Depends(get_current_user)):
    """事件 → 处理器链的路由表，供答辩展示与前端解释。"""
    from ..services.event_bus import ROUTES

    items = [
        {
            "type": event_type,
            "handlers": handlers,
            "auto": auto,
            "needs_confirmation": needs_confirm,
            "note": note,
        }
        for event_type, (handlers, auto, needs_confirm, note) in ROUTES.items()
    ]
    return {"total": len(items), "items": items}
