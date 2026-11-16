import json
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import ReplanLog, Task, User
from ..schemas import (
    ApplyForecastIn,
    AutoAdjustOut,
    ForecastOut,
    InsightsOut,
    RestOut,
    TwinForecastOut,
    TwinOut,
)
from ..services.ai_content import ai_forecast_strategy, ai_insight_report
from ..services.auto_schedule import auto_adjust_today
from ..services.forecast import build_forecast
from ..services.insights import build_insights
from ..services.planner import replan
from ..services.twin import build_forecast as build_twin_forecast, build_twin
from .goals import build_goal_out

router = APIRouter(tags=["学情洞察与冲刺"])


@router.get("/goals/{goal_id}/twin", response_model=TwinOut)
def goal_twin(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TwinOut:
    goal = get_user_goal(goal_id, user, db)
    return TwinOut(**build_twin(db, user, goal))


@router.get("/goals/{goal_id}/twin/forecast", response_model=TwinForecastOut)
def goal_twin_forecast(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TwinForecastOut:
    goal = get_user_goal(goal_id, user, db)
    return TwinForecastOut(**build_twin_forecast(db, user, goal))


@router.get("/goals/{goal_id}/insights", response_model=InsightsOut)
async def goal_insights(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InsightsOut:
    goal = get_user_goal(goal_id, user, db)
    data = build_insights(db, user.id, goal.id)
    data["ai_report"] = await ai_insight_report(db, user, goal, data)
    return InsightsOut(**data)


@router.get("/goals/{goal_id}/forecast", response_model=ForecastOut)
async def goal_forecast(
    goal_id: int,
    daily_minutes: Optional[int] = Query(default=None, ge=20, le=600),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ForecastOut:
    goal = get_user_goal(goal_id, user, db)
    data = build_forecast(db, user, goal, daily_minutes=daily_minutes)
    strategy = await ai_forecast_strategy(data, goal)
    data["ai_strategy"] = strategy["text"]
    data["ai_engine"] = strategy["engine"]
    return ForecastOut(**data)


@router.post("/goals/{goal_id}/apply-forecast")
def apply_forecast(
    goal_id: int,
    payload: ApplyForecastIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    goal.daily_minutes = payload.daily_minutes
    db.commit()
    db.refresh(goal)
    result = replan(db, user.id, goal, trigger="forecast")
    forecast = build_forecast(db, user, goal)
    auto = auto_adjust_today(db, user, goal)
    return {
        "goal": build_goal_out(db, user.id, goal).model_dump(mode="json"),
        "forecast": forecast,
        "changes": result["changes"],
        "auto_adjust": auto,
    }


@router.post("/goals/{goal_id}/rest", response_model=RestOut)
def start_rest(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RestOut:
    goal = get_user_goal(goal_id, user, db)
    today = date.today()
    pending = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        ).order_by(Task.priority.desc())
    ).all()

    if len(pending) <= 1:
        return RestOut(moved=0, kept=len(pending), summary="今日任务已经足够精简，先把剩下的完成即可。")

    keep = pending[:1]
    moving = pending[1:]
    latest = goal.exam_date - timedelta(days=1)
    moved = 0
    for task in moving:
        target = today + timedelta(days=1)
        while target <= latest:
            occupied = sum(
                item.duration_min
                for item in db.scalars(
                    select(Task).where(
                        Task.user_id == user.id,
                        Task.goal_id == goal.id,
                        Task.day == target,
                        Task.status == "pending",
                    )
                ).all()
            )
            if occupied + task.duration_min <= goal.daily_minutes:
                break
            target += timedelta(days=1)
        if target > latest:
            task.status = "skipped"
            task.reason = task.reason + "（疲劳降载，已取消）"
        else:
            task.day = target
            task.reason = task.reason + f"（疲劳降载，从 {today.isoformat()} 顺延到 {target.isoformat()}）"
            moved += 1
    db.add(
        ReplanLog(
            user_id=user.id,
            goal_id=goal.id,
            trigger="rest",
            changes=json.dumps(
                [
                    {
                        "kind": "rest",
                        "detail": f"疲劳干预：保留 1 个最高优先级任务，顺延 {moved} 个任务",
                        "task_id": None,
                    }
                ],
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return RestOut(
        moved=moved,
        kept=len(keep),
        summary=f"已按疲劳指数降载：今天只保留「{keep[0].title}」，其余 {moved} 个任务顺延。",
    )