from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import LearningExperiment, User
from ..schemas import (
    ExperimentCreateIn,
    ExperimentFinishIn,
    ExperimentOut,
    ExperimentReportOut,
)
from ..services.experiments import (
    build_report,
    experiment_dict,
    finish_experiment,
    list_experiments,
    start_experiment,
)

router = APIRouter(tags=["策略实验室"])

VALID_STRATEGIES = {"read", "practice", "flashcard", "ai_tutor"}


@router.get("/goals/{goal_id}/experiments")
def experiments(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return list_experiments(db, user.id, goal.id)


@router.post("/goals/{goal_id}/experiments", response_model=ExperimentOut, status_code=201)
def create_experiment(
    goal_id: int,
    payload: ExperimentCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExperimentOut:
    if payload.strategy not in VALID_STRATEGIES:
        raise HTTPException(status_code=400, detail="学习方式必须是 read / practice / flashcard / ai_tutor")
    goal = get_user_goal(goal_id, user, db)
    experiment = start_experiment(db, user, goal, payload.strategy, payload.days)
    return ExperimentOut(**experiment_dict(experiment))


@router.post("/experiments/{experiment_id}/finish", response_model=ExperimentOut)
def finish(
    experiment_id: int,
    payload: ExperimentFinishIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExperimentOut:
    experiment = db.get(LearningExperiment, experiment_id)
    if not experiment or experiment.user_id != user.id:
        raise HTTPException(status_code=404, detail="实验不存在")
    if experiment.status == "finished":
        return ExperimentOut(**experiment_dict(experiment))
    updated = finish_experiment(
        db,
        user,
        experiment,
        payload.immediate_score,
        payload.delayed_score,
        payload.note,
    )
    return ExperimentOut(**experiment_dict(updated))

@router.get("/experiments/{experiment_id}/report", response_model=ExperimentReportOut)
def experiment_report(
    experiment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExperimentReportOut:
    experiment = db.get(LearningExperiment, experiment_id)
    if not experiment or experiment.user_id != user.id:
        raise HTTPException(status_code=404, detail="实验不存在")
    return ExperimentReportOut(**build_report(db, experiment))