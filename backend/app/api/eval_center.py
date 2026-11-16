"""AI 可靠性评测中心接口。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..services.eval_center import list_runs, run_eval
from ..services.synthetic import generate_students

router = APIRouter(tags=["AI 可靠性评测"])


class SyntheticIn(BaseModel):
    count: int = Field(default=10, ge=1, le=50)
    seed: int = Field(default=42, ge=1, le=9999)


@router.post("/eval/run")
async def eval_run(
    limit: int = Query(default=6, ge=1, le=6),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await run_eval(db, user, limit)


@router.get("/eval/runs")
def eval_runs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"runs": list_runs(db, user)}

@router.post("/eval/synthetic-students")
def synthetic_students(
    payload: SyntheticIn,
    user: User = Depends(get_current_user),
):
    return generate_students(payload.count, payload.seed)