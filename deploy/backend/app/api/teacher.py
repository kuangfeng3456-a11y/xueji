"""教师教学决策台接口：仅班级创建者可访问。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import SchoolClass, User
from ..services.teacher import teacher_dashboard

router = APIRouter(tags=["教师决策台"])


@router.get("/classes/{class_id}/teacher-dashboard")
def teacher_class_dashboard(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="班级不存在")
    if school_class.owner_id != user.id:
        raise HTTPException(status_code=403, detail="仅班级创建者可访问教师决策台")
    return teacher_dashboard(db, school_class)