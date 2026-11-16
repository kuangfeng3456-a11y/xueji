"""教师工作台、班级对比报表与教务对接。学生账号不可访问。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_staff
from ..models import User
from ..services import campus as campus_service

router = APIRouter(prefix="/campus", tags=["教师工作台与教务对接"])


class PushIn(BaseModel):
    class_id: int


def _ids(raw: str) -> List[int]:
    items = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            items.append(int(part))
        except ValueError:
            raise HTTPException(status_code=400, detail="班级编号格式不正确")
    return items


@router.get("/workbench")
def workbench(db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    return campus_service.workbench(db, user)


@router.get("/classes/compare")
def compare(
    ids: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> dict:
    try:
        return campus_service.compare_classes(db, user, _ids(ids))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/bridge")
def bridge_status(user: User = Depends(require_staff)) -> dict:
    return campus_service.bridge_target()


@router.post("/bridge/sync")
def bridge_sync(db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    return campus_service.sync_roster(db, user)


@router.post("/bridge/push")
def bridge_push(
    payload: PushIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> dict:
    try:
        return campus_service.push_summary(db, user, payload.class_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/bridge/logs")
def bridge_logs(db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    return {"items": campus_service.recent_logs(db, user)}
