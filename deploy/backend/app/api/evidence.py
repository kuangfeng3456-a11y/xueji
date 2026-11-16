from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..schemas import (
    CognitiveLoadApplyIn,
    CognitiveLoadOut,
    EvidenceOut,
)
from ..services.cognitive_load import apply_load, compute_load
from ..services.evidence import list_evidence

router = APIRouter(tags=["证据链与认知负荷"])


@router.get("/goals/{goal_id}/evidence", response_model=List[EvidenceOut])
def evidence_chain(
    goal_id: int,
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[EvidenceOut]:
    goal = get_user_goal(goal_id, user, db)
    return [EvidenceOut(**item) for item in list_evidence(db, user, goal.id, kind, limit)]


@router.get("/goals/{goal_id}/cognitive-load", response_model=CognitiveLoadOut)
def cognitive_load(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CognitiveLoadOut:
    goal = get_user_goal(goal_id, user, db)
    return CognitiveLoadOut(**compute_load(db, user, goal))


@router.post("/goals/{goal_id}/cognitive-load/apply")
def apply_cognitive_load(
    goal_id: int,
    payload: CognitiveLoadApplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    return apply_load(db, user, goal, payload.action)