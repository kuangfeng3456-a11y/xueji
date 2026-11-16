"""知识漏洞早期预警接口：风险预测、历史、验证题与反馈。"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import KnowledgePoint, RiskPrediction, User
from ..schemas import RiskFeedbackIn, RiskForecastOut, RiskVerifyIn
from ..services import risk_forecast
from ..services.probes import generate_probes, probe_to_dict

router = APIRouter(tags=["知识漏洞预警"])


@router.get("/goals/{goal_id}/risk-forecast", response_model=RiskForecastOut)
def risk_forecast_list(
    goal_id: int,
    high: float = Query(default=risk_forecast.DEFAULT_HIGH, ge=20, le=100),
    medium: float = Query(default=risk_forecast.DEFAULT_MEDIUM, ge=10, le=95),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RiskForecastOut:
    goal = get_user_goal(goal_id, user, db)
    data = risk_forecast.list_risks(db, user, goal, high=high, medium=medium)
    return RiskForecastOut(**data)


@router.get("/goals/{goal_id}/risk-forecast/history")
def risk_forecast_history(
    goal_id: int,
    kp_id: Optional[int] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return {
        "history": risk_forecast.risk_history(db, user, goal, kp_id=kp_id, limit=limit)
    }


@router.post("/risk-forecast/{prediction_id}/verify")
def risk_forecast_verify(
    prediction_id: int,
    payload: RiskVerifyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prediction = db.get(RiskPrediction, prediction_id)
    if prediction is None or prediction.user_id != user.id:
        raise ValueError("风险记录不存在")
    goal = get_user_goal(prediction.goal_id, user, db)
    return risk_forecast.apply_verification(db, user, goal, prediction_id, payload.passed)


@router.post("/risk-forecast/{prediction_id}/feedback")
def risk_forecast_feedback(
    prediction_id: int,
    payload: RiskFeedbackIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prediction = db.get(RiskPrediction, prediction_id)
    if prediction is None or prediction.user_id != user.id:
        raise ValueError("风险记录不存在")
    goal = get_user_goal(prediction.goal_id, user, db)
    return risk_forecast.submit_feedback(db, user, goal, prediction_id, payload.verdict)


@router.post("/risk-forecast/{prediction_id}/questions")
async def risk_forecast_questions(
    prediction_id: int,
    count: int = Query(default=2, ge=1, le=3),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prediction = db.get(RiskPrediction, prediction_id)
    if prediction is None or prediction.user_id != user.id:
        raise ValueError("风险记录不存在")
    goal = get_user_goal(prediction.goal_id, user, db)
    point = db.get(KnowledgePoint, prediction.kp_id)
    if point is None:
        raise ValueError("关联知识点不存在")
    probes = await generate_probes(db, user, goal, kind="probe", count=count, kp_id=point.id)
    point_map = {point.id: point}
    return {
        "prediction_id": prediction_id,
        "kp_id": point.id,
        "kp_name": point.name,
        "questions": [probe_to_dict(item, point_map) for item in probes],
    }