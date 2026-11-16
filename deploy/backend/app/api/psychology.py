import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import PsychologyAssessment, User
from ..services import psychology
from ..services.safety_events import record_safety_event
from ..services.wellbeing import crisis_check as wellbeing_check

router = APIRouter(prefix="/psychology", tags=["心理评估"])


class AssessIn(BaseModel):
    scale: str = Field(min_length=2, max_length=32)
    answers: List[int] = Field(min_length=1, max_length=40)


class CrisisIn(BaseModel):
    text: str = Field(default="", max_length=2000)


@router.post("/crisis-check")
def crisis_check(
    payload: CrisisIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = wellbeing_check(payload.text)
    if result.get("level") == "crisis":
        record_safety_event(db, user.id, "crisis", "high", "referred_12356")
        db.commit()
    return result


@router.get("/scales")
def scales(user: User = Depends(get_current_user)) -> dict:
    return {"scales": psychology.scale_list(), "resources": psychology.RESOURCES}


@router.get("/scales/{key}")
def scale_detail(key: str, user: User = Depends(get_current_user)) -> dict:
    scale = psychology.get_scale(key)
    if not scale:
        raise HTTPException(status_code=404, detail="量表不存在")
    return {
        "key": scale["key"],
        "name": scale["name"],
        "intro": scale["intro"],
        "questions": scale["questions"],
        "options": scale["options"],
        "max_score": scale["max_score"],
        "source": scale["source"],
    }


@router.post("/assess")
async def assess(
    payload: AssessIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        result = await psychology.assess(payload.scale, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    record = PsychologyAssessment(
        user_id=user.id,
        scale=payload.scale,
        score=result["score"],
        max_score=result["max_score"],
        level=result["level"],
        answers=json.dumps(payload.answers),
        summary=result["interpretation"]["text"][:2000],
        engine=result["interpretation"]["engine"],
    )
    db.add(record)
    if result.get("safety", {}).get("urgent"):
        record_safety_event(db, user.id, "crisis", "high", "self_report_flagged")
    db.commit()
    db.refresh(record)
    result["id"] = record.id
    return result


@router.get("/history")
def history(
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = db.scalars(
        select(PsychologyAssessment)
        .where(PsychologyAssessment.user_id == user.id)
        .order_by(PsychologyAssessment.created_at.desc())
        .limit(min(max(limit, 1), 30))
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "scale": row.scale,
                "score": row.score,
                "max_score": row.max_score,
                "level": row.level,
                "summary": row.summary,
                "engine": row.engine,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }