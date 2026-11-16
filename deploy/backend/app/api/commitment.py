"""C3 实施意图微承诺 API（文档 4.4）。"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Commitment, Task, User
from ..services import commitment

router = APIRouter(tags=["微承诺"])


class CommitmentCreateIn(BaseModel):
    goal_id: int
    task_id: Optional[int] = None
    if_condition: str
    then_action: str
    due_date: Optional[date] = None
    source: str = "user"


class CommitmentActionIn(BaseModel):
    note: str = ""


@router.get("/commitments/today")
def commitments_today(
    goal_id: int,
    day: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """今日承诺列表 + 活跃数（过期未确认的先惰性结算再返回）。"""
    goal = get_user_goal(goal_id, user, db)
    return commitment.today_list(db, user.id, goal.id, day or date.today())


@router.get("/commitments/suggestions")
def commitments_suggestions(
    goal_id: int,
    day: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """教练生成的「如果—那么」候选承诺（规则模板，可复算）。"""
    goal = get_user_goal(goal_id, user, db)
    suggestions = commitment.generate_suggestions(db, goal, day or date.today())
    active = (
        db.query(Commitment)
        .filter(Commitment.user_id == user.id, Commitment.status == "pending")
        .count()
    )
    return {
        "suggestions": suggestions,
        "active_count": active,
        "max_active": commitment.MAX_ACTIVE,
    }


@router.post("/commitments")
def create_commitment(
    payload: CommitmentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """采纳教练建议或自建承诺；活跃承诺有上限，贵精不贵多。"""
    goal = get_user_goal(payload.goal_id, user, db)
    if_condition = (payload.if_condition or "").strip()
    then_action = (payload.then_action or "").strip()
    if not if_condition or not then_action:
        raise HTTPException(422, "「如果」与「那么」都不能为空")
    if len(if_condition) > 240 or len(then_action) > 240:
        raise HTTPException(422, "承诺文本过长，请精简到 240 字以内")
    active = (
        db.query(Commitment)
        .filter(Commitment.user_id == user.id, Commitment.status == "pending")
        .count()
    )
    if active >= commitment.MAX_ACTIVE:
        raise HTTPException(
            409, f"已有 {active} 条待履行承诺，先完成或取消一条再加（微承诺贵精不贵多）"
        )
    if payload.task_id:
        task = (
            db.query(Task)
            .filter(Task.id == payload.task_id, Task.goal_id == goal.id)
            .first()
        )
        if not task:
            raise HTTPException(404, "关联的任务不存在")
    item = Commitment(
        user_id=user.id,
        goal_id=goal.id,
        task_id=payload.task_id,
        if_condition=if_condition,
        then_action=then_action,
        due_date=payload.due_date or date.today(),
        source=payload.source if payload.source in ("coach", "user") else "user",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return commitment._serialize(item)


@router.post("/commitments/{commitment_id}/fulfill")
def fulfill_commitment(
    commitment_id: int,
    payload: CommitmentActionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """打卡履行：做了就记一笔，沉淀习惯数据。"""
    from datetime import datetime

    item = (
        db.query(Commitment)
        .filter(Commitment.id == commitment_id, Commitment.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(404, "承诺不存在")
    if item.status not in ("pending", "missed"):
        raise HTTPException(409, f"当前状态为 {item.status}，不能打卡")
    item.status = "fulfilled"
    item.fulfilled_at = datetime.utcnow()
    item.checkin_note = (payload.note or "").strip()[:240]
    # 逾期后补打卡：从 missed 里捞回来，如实保留结算痕迹
    item.settled_at = None
    db.commit()
    return commitment._serialize(item)


@router.post("/commitments/{commitment_id}/cancel")
def cancel_commitment(
    commitment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(Commitment)
        .filter(Commitment.id == commitment_id, Commitment.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(404, "承诺不存在")
    if item.status not in ("pending", "missed"):
        raise HTTPException(409, f"当前状态为 {item.status}，不能取消")
    item.status = "cancelled"
    db.commit()
    return commitment._serialize(item)


@router.get("/commitments/stats")
def commitments_stats(
    goal_id: int,
    window_days: int = Query(28, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """习惯数据：履行率 + 承诺履行与当日完成率的相关性（文档 C3 指标）。"""
    goal = get_user_goal(goal_id, user, db)
    commitment.settle_overdue(db, user.id, goal.id)
    return commitment.stats(db, user.id, goal.id, window_days)
