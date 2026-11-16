import json
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.coach import coach_message
from ..agents.skills import list_skills
from ..cache import cache
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Goal, KnowledgePoint, Mastery, Mistake, ReplanLog, Task, User
from ..schemas import (
    AutoAdjustOut,
    DashboardOut,
    GoalOut,
    MasteryOut,
    MistakeOut,
    ReplanChange,
    RhythmOut,
    UserOut,
)
from ..services.auto_schedule import auto_adjust_today
from ..services.planner import task_to_dict
from ..services.rhythm import build_rhythm
from ..services.rules import calc_streak, days_left
from .goals import build_goal_out

router = APIRouter(tags=["首页与元信息"])


def _recent_changes(db: Session, user_id: int, goal_id: int) -> List[ReplanChange]:
    log = db.scalar(
        select(ReplanLog)
        .where(ReplanLog.user_id == user_id, ReplanLog.goal_id == goal_id)
        .order_by(ReplanLog.created_at.desc())
    )
    if not log:
        return []
    try:
        items = json.loads(log.changes)
    except Exception:
        return []
    return [ReplanChange(**item) for item in items][:5]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    goal_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DashboardOut:
    today = date.today()
    goal: Optional[Goal] = None
    if goal_id is not None:
        goal = get_user_goal(goal_id, user, db)
    else:
        goal = db.scalar(
            select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc()).limit(1)
        )

    if goal is None:
        return DashboardOut(
            user=UserOut.model_validate(user),
            goal=None,
            today_tasks=[],
            today_minutes=0,
            streak=0,
            mastery=[],
            weak_points=[],
            mistake_count_7d=0,
            recent_mistakes=[],
            coach_message="欢迎来到学迹。先创建一个考试目标，再导入资料，我会为你排出每天该学什么。",
            latest_changes=[],
            auto_adjust=None,
            server_date=today,
        )

    # 剩余时间不足、任务逾期或今天为空时，系统自动调整，用户无需手动点重排
    try:
        auto_adjust = AutoAdjustOut(**auto_adjust_today(db, user, goal, today))
    except Exception:
        db.rollback()
        auto_adjust = AutoAdjustOut(
            days_left=days_left(goal.exam_date, today),
            force_mode=bool(goal.force_mode),
        )

    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_map = {point.id: point for point in points}
    mastery_rows = db.scalars(
        select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id.in_([p.id for p in points] or [0]))
    ).all()
    mastery_map = {row.kp_id: row for row in mastery_rows}

    mastery_items = [
        MasteryOut(
            kp_id=point.id,
            kp_name=point.name,
            value=mastery_map.get(point.id).value if point.id in mastery_map else 0.0,
            next_review_at=mastery_map.get(point.id).next_review_at if point.id in mastery_map else None,
        )
        for point in points
    ]
    weak_points = sorted(mastery_items, key=lambda item: item.value)[:5]

    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status != "skipped",
        ).order_by(Task.priority.desc())
    ).all()
    today_tasks = [task_to_dict(task, point_map) for task in tasks]
    today_minutes = sum(task.duration_min for task in tasks)

    done_days = set(
        db.scalars(
            select(Task.day).where(
                Task.user_id == user.id,
                Task.goal_id == goal.id,
                Task.status == "done",
            )
        ).all()
    )
    streak = calc_streak(done_days, today)

    since = datetime.combine(today - timedelta(days=7), datetime.min.time())
    recent_mistakes_rows = db.scalars(
        select(Mistake)
        .where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
        .order_by(Mistake.created_at.desc())
        .limit(5)
    ).all()
    mistake_count = db.scalar(
        select(func.count(Mistake.id)).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= since,
        )
    ) or 0
    recent_mistakes = [
        MistakeOut(
            id=row.id,
            question=row.question,
            user_answer=row.user_answer,
            correct_answer=row.correct_answer,
            category=row.category,
            category_label=row.category_label,
            suggestion=row.suggestion,
            source=row.source,
            created_at=row.created_at,
            kp_id=row.kp_id,
            kp_name=point_map.get(row.kp_id).name if row.kp_id and row.kp_id in point_map else None,
        )
        for row in recent_mistakes_rows
    ]

    remain = days_left(goal.exam_date, today)
    cache_key = f"coach:{user.id}:{goal.id}:{today.isoformat()}:{len(tasks)}:{len([t for t in tasks if t.status == 'done'])}"
    cached = cache.get_json(cache_key)
    if cached:
        coach_text = cached.get("text", "")
    else:
        coach_text = await coach_message(
            user, goal, tasks, streak, mistake_count, remain
        )
        cache.set_json(cache_key, {"text": coach_text}, ttl=600)

    return DashboardOut(
        user=UserOut.model_validate(user),
        goal=build_goal_out(db, user.id, goal),
        today_tasks=today_tasks,
        today_minutes=today_minutes,
        streak=streak,
        mastery=mastery_items,
        weak_points=weak_points,
        mistake_count_7d=mistake_count,
        recent_mistakes=recent_mistakes,
        coach_message=coach_text,
        latest_changes=_recent_changes(db, user.id, goal.id),
        rhythm=RhythmOut(**build_rhythm(db, user.id, goal.id, today=today)),
        auto_adjust=auto_adjust,
        server_date=today,
    )


@router.get("/goals/{goal_id}/rhythm", response_model=RhythmOut)
def goal_rhythm(
    goal_id: int,
    days: int = Query(default=28, ge=7, le=60),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RhythmOut:
    """双维度画像的第二维：常学时段、拖延规律与近期完成率。"""
    goal = get_user_goal(goal_id, user, db)
    return RhythmOut(**build_rhythm(db, user.id, goal.id, days=days))


@router.get("/skills")
def skills() -> dict:
    return {"skills": list_skills(), "count": len(list_skills())}


@router.get("/meta")
def meta() -> dict:
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "llm_enabled": bool(settings.LLM_BASE_URL and settings.LLM_API_KEY),
        "llm_model": settings.LLM_MODEL if settings.LLM_API_KEY else None,
        "cache_backend": cache.backend,
        "skills": [skill["name"] for skill in list_skills()],
        # 仅在演示环境显式配置 DEMO_HINT 时才有值；商用部署默认为空，
        # 前端据此决定是否展示演示账号，避免明文密码进入生产页面。
        "demo_hint": settings.DEMO_HINT,
    }