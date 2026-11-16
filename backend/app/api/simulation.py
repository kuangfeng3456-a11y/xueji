from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..schemas import SimulationOut
from ..services.evidence import record_evidence
from ..services.simulation import build_simulation

router = APIRouter(tags=["未来模拟实验室"])


@router.get("/goals/{goal_id}/simulate", response_model=SimulationOut)
def simulate(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SimulationOut:
    goal = get_user_goal(goal_id, user, db)
    result = build_simulation(db, user, goal)
    record_evidence(
        db,
        user.id,
        goal.id,
        "simulation",
        "未来模拟实验室",
        {
            "current_mastery": result.get("current_mastery"),
            "plans": result.get("plans"),
            "uncertainty": result.get("uncertainty"),
        },
        result.get("recommendation", ""),
        engine="rule",
        commit=True,
    )
    return SimulationOut(**result)