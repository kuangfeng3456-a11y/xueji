from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import (
    Goal,
    KnowledgeGap,
    KnowledgePoint,
    LearningExperiment,
    Task,
    User,
)
from ..schemas import CockpitOut, ReadinessOut, RiskOut, TaskOut
from ..services.planner import task_to_dict
from ..services.readiness import build_risks, compute_readiness

router = APIRouter(tags=["学习驾驶舱"])


@router.get("/goals/{goal_id}/cockpit", response_model=CockpitOut)
def cockpit(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CockpitOut:
    goal = get_user_goal(goal_id, user, db)
    today = date.today()
    readiness = compute_readiness(db, user, goal, today)
    risks = build_risks(db, user, goal, today, readiness=readiness)

    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_map = {point.id: point for point in points}
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        ).order_by(Task.priority.desc())
    ).all()
    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id,
            KnowledgeGap.goal_id == goal.id,
        )
    ).all()
    experiments = db.scalars(
        select(LearningExperiment).where(
            LearningExperiment.user_id == user.id,
            LearningExperiment.goal_id == goal.id,
        )
    ).all()

    return CockpitOut(
        readiness=ReadinessOut(**readiness),
        risks=[RiskOut(**risk) for risk in risks],
        critical_tasks=[TaskOut(**task_to_dict(task, point_map)) for task in tasks[:3]],
        gap_count=len([gap for gap in gaps if gap.status == "candidate"]),
        verified_gap_count=len([gap for gap in gaps if gap.status == "verified"]),
        experiment_count=len(experiments),
    )