from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal, require_staff
from ..models import User
from ..schemas import ApplyPackageIn, SkillPackageCreateIn, SkillPackageOut
from ..services.skill_packages import (
    apply_package,
    create_package,
    package_views,
    redeem_package,
    review_package,
    review_queue,
    share_package,
)

router = APIRouter(prefix="/skill-packages", tags=["学科 Skill 包市场"])


class ReviewIn(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=200)


class RedeemIn(BaseModel):
    share_code: str = Field(min_length=4, max_length=16)
    goal_id: int


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
    user: User = Depends(require_staff),
) -> dict:
    try:
        return create_package(
            db,
            payload.name,
            payload.subject,
            payload.description,
            payload.tags,
            [item.model_dump() for item in payload.points],
            author_id=user.id,
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
        text = str(exc)
        code = 400 if "审核" in text or "分享" in text else 404
        raise HTTPException(status_code=code, detail=text)


def _bad(exc: ValueError, default: int = 400) -> HTTPException:
    text = str(exc)
    code = 404 if "不存在" in text or "无效" in text else default
    return HTTPException(status_code=code, detail=text)


@router.get("/review")
def queue(
    mine: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> dict:
    author_id = user.id if mine else None
    return {"items": review_queue(db, author_id)}


@router.post("/redeem")
def redeem(
    payload: RedeemIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(payload.goal_id, user, db)
    try:
        return redeem_package(db, user.id, goal, payload.share_code)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/{slug}/review")
def review(
    slug: str,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> dict:
    try:
        return review_package(db, user.id, slug, payload.action, payload.note)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/{slug}/share")
def share(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> dict:
    try:
        return share_package(db, user.id, slug)
    except ValueError as exc:
        raise _bad(exc)
