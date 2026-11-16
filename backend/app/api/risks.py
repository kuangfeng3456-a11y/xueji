from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..schemas import RiskOut
from ..services.evidence import record_evidence
from ..services.readiness import build_risks, resolve_risk

router = APIRouter(tags=["风险救援中心"])


@router.get("/goals/{goal_id}/risks", response_model=List[RiskOut])
def risks(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[RiskOut]:
    goal = get_user_goal(goal_id, user, db)
    return [RiskOut(**risk) for risk in build_risks(db, user, goal)]


@router.post("/goals/{goal_id}/risks/{code}/resolve")
def resolve(
    goal_id: int,
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    result = resolve_risk(db, user, goal, code)
    record_evidence(
        db,
        user.id,
        goal.id,
        f"risk_{code}",
        f"{code} 风险救援",
        {
            "before": result["before"],
            "after": result["after"],
            "changes": result["changes"],
        },
        result["message"],
        engine="rule",
        commit=True,
    )
    return result