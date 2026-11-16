from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..schemas import ApplyPackageIn, SkillPackageCreateIn, SkillPackageOut
from ..services.skill_packages import apply_package, create_package, package_views

router = APIRouter(prefix="/skill-packages", tags=["学科 Skill 包市场"])


@router.get("", response_model=List[SkillPackageOut])
def list_packages(
    goal_id: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SkillPackageOut]:
    goal = None
    if goal_id:
        goal = get_user_goal(goal_id, user, db)
    return [SkillPackageOut(**item) for item in package_views(db, goal)]


@router.post("", status_code=201)
def create(
    payload: SkillPackageCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return create_package(
            db,
            payload.name,
            payload.subject,
            payload.description,
            payload.tags,
            [item.model_dump() for item in payload.points],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{slug}/apply")
def apply(
    slug: str,
    payload: ApplyPackageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(payload.goal_id, user, db)
    try:
        return apply_package(db, user.id, goal, slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
