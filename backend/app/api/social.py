import random
import string
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Buddy, ClassMember, SchoolClass, User
from ..schemas import (
    BuddyAdd,
    BuddyProfile,
    ClassCreate,
    ClassDashboardOut,
    ClassJoin,
    ClassMemberProfile,
    UserOut,
)
from ..services.social import build_class_dashboard, buddy_profiles, class_members, member_profile

router = APIRouter(tags=["班级看板与学习搭子"])


def _generate_invite_code(db: Session) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(30):
        code = "".join(random.choice(alphabet) for _ in range(6))
        if not db.scalar(select(SchoolClass).where(SchoolClass.invite_code == code)):
            return code
    raise HTTPException(status_code=500, detail="邀请码生成失败，请重试")


def _class_brief(db: Session, school_class: SchoolClass, user: User) -> dict:
    members = class_members(db, school_class.id)
    role = "owner" if school_class.owner_id == user.id else "student"
    return {
        "id": school_class.id,
        "name": school_class.name,
        "description": school_class.description,
        "invite_code": school_class.invite_code,
        "owner_id": school_class.owner_id,
        "owner_name": db.get(User, school_class.owner_id).nickname if db.get(User, school_class.owner_id) else "",
        "member_count": len(members),
        "is_owner": school_class.owner_id == user.id,
        "role": role,
        "created_at": school_class.created_at.isoformat(),
    }


def _membership(db: Session, class_id: int, user_id: int) -> Optional[ClassMember]:
    return db.scalar(
        select(ClassMember).where(ClassMember.class_id == class_id, ClassMember.user_id == user_id)
    )


@router.get("/classes")
def list_classes(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> List[dict]:
    member_rows = db.scalars(select(ClassMember).where(ClassMember.user_id == user.id)).all()
    class_ids = [row.class_id for row in member_rows]
    classes = (
        db.scalars(select(SchoolClass).where(SchoolClass.id.in_(class_ids)).order_by(SchoolClass.created_at.desc())).all()
        if class_ids
        else []
    )
    return [_class_brief(db, school_class, user) for school_class in classes]


@router.post("/classes", status_code=201)
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    school_class = SchoolClass(
        name=payload.name.strip(),
        description=payload.description.strip(),
        owner_id=user.id,
        invite_code=_generate_invite_code(db),
    )
    db.add(school_class)
    db.flush()
    db.add(ClassMember(class_id=school_class.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(school_class)
    return _class_brief(db, school_class, user)


@router.post("/classes/join")
def join_class(
    payload: ClassJoin,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    code = payload.invite_code.strip().upper()
    school_class = db.scalar(select(SchoolClass).where(SchoolClass.invite_code == code))
    if not school_class:
        raise HTTPException(status_code=404, detail="邀请码无效，请向老师或班长确认")
    if _membership(db, school_class.id, user.id):
        return _class_brief(db, school_class, user)
    db.add(ClassMember(class_id=school_class.id, user_id=user.id, role="student"))
    db.commit()
    return _class_brief(db, school_class, user)


@router.post("/classes/{class_id}/leave", status_code=204)
def leave_class(
    class_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="班级不存在")
    if school_class.owner_id == user.id:
        raise HTTPException(status_code=400, detail="创建者不能退出班级，可删除班级")
    membership = _membership(db, class_id, user.id)
    if not membership:
        raise HTTPException(status_code=404, detail="你不在该班级中")
    db.delete(membership)
    db.commit()


@router.delete("/classes/{class_id}", status_code=204)
def delete_class(
    class_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="班级不存在")
    if school_class.owner_id != user.id:
        raise HTTPException(status_code=403, detail="只有创建者可以删除班级")
    db.query(ClassMember).filter(ClassMember.class_id == class_id).delete(synchronize_session=False)
    db.delete(school_class)
    db.commit()


@router.get("/classes/{class_id}/dashboard", response_model=ClassDashboardOut)
def class_dashboard(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClassDashboardOut:
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="班级不存在")
    if not _membership(db, class_id, user.id):
        raise HTTPException(status_code=403, detail="请先加入班级")
    return ClassDashboardOut(**build_class_dashboard(db, school_class))


@router.delete("/classes/{class_id}/members/{member_id}", status_code=204)
def remove_member(
    class_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="班级不存在")
    if school_class.owner_id != user.id:
        raise HTTPException(status_code=403, detail="只有创建者可以移除成员")
    if member_id == user.id:
        raise HTTPException(status_code=400, detail="不能移除自己")
    membership = _membership(db, class_id, member_id)
    if not membership:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.delete(membership)
    db.commit()


@router.get("/users/search")
def search_users(
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[dict]:
    keyword = (q or "").strip()
    if len(keyword) < 1:
        return []
    rows = db.scalars(
        select(User)
        .where(User.id != user.id)
        .where((User.username.contains(keyword)) | (User.nickname.contains(keyword)))
        .limit(10)
    ).all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "nickname": row.nickname,
            "school": row.school,
        }
        for row in rows
    ]


@router.get("/buddies", response_model=List[BuddyProfile])
def list_buddies(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[BuddyProfile]:
    return [BuddyProfile(**profile) for profile in buddy_profiles(db, user)]


@router.post("/buddies", response_model=BuddyProfile, status_code=201)
def add_buddy(
    payload: BuddyAdd,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BuddyProfile:
    buddy = db.scalar(select(User).where(User.username == payload.username.strip()))
    if not buddy:
        raise HTTPException(status_code=404, detail="没有找到该用户名")
    if buddy.id == user.id:
        raise HTTPException(status_code=400, detail="不能添加自己为学习搭子")
    exists = db.scalar(select(Buddy).where(Buddy.user_id == user.id, Buddy.buddy_id == buddy.id))
    if not exists:
        db.add(Buddy(user_id=user.id, buddy_id=buddy.id))
        db.add(Buddy(user_id=buddy.id, buddy_id=user.id))
        db.commit()
    profile = member_profile(db, buddy)
    profile["is_me"] = False
    return BuddyProfile(**profile)


@router.delete("/buddies/{buddy_id}", status_code=204)
def remove_buddy(
    buddy_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    db.query(Buddy).filter(
        ((Buddy.user_id == user.id) & (Buddy.buddy_id == buddy_id))
        | ((Buddy.user_id == buddy_id) & (Buddy.buddy_id == user.id))
    ).delete(synchronize_session=False)
    db.commit()