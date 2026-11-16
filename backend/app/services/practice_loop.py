"""今日闭环、难点回流复习、会话收束与班级布置。间隔仍用既有 REVIEW_INTERVALS。"""

import json
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ClassAssignment,
    ClassMember,
    CoachMessage,
    CoachSession,
    DailyReview,
    Goal,
    KnowledgePoint,
    QuizAttempt,
    ReviewCard,
    SchoolClass,
    SkillPackage,
    Task,
    User,
)
from .mastery_service import ensure_mastery
from .skill_packages import ensure_packages
from .social import class_members


def enqueue_point(db: Session, user: User, goal: Goal, kp_id: Optional[int] = None, name: str = "") -> dict:
    """把一个知识点放进今天的复习队列，不改复习阶段，也不改间隔表。"""
    point = None
    if kp_id:
        point = db.get(KnowledgePoint, kp_id)
        if point is None or point.goal_id != goal.id:
            raise ValueError("知识点不存在")
    else:
        clean = (name or "").strip()
        if not clean:
            raise ValueError("请指定要复习的知识点")
        point = db.scalar(
            select(KnowledgePoint).where(
                KnowledgePoint.goal_id == goal.id,
                func.lower(KnowledgePoint.name) == clean.lower(),
            )
        )
        if point is None:
            raise ValueError("当前目标里没有这个知识点，请先导入学科包")
    record = ensure_mastery(db, user.id, point)
    today = date.today()
    record.next_review_at = today
    card = db.scalar(select(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.kp_id == point.id))
    if card is None:
        card = ReviewCard(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            stability=1.0,
            next_review=today,
        )
        db.add(card)
    else:
        card.next_review = today
    db.commit()
    return {
        "kp_id": point.id,
        "name": point.name,
        "next_review_at": today.isoformat(),
        "review_stage": record.review_stage,
        "detail": f"「{point.name}」已加入今天的闪卡复习，复习间隔没有被改写。",
    }


def loop_status(db: Session, user: User, goal: Optional[Goal], today: Optional[date] = None) -> dict:
    today = today or date.today()
    if goal is None:
        return {
            "loop_steps": [],
            "week_activity": [],
            "next_step": "先设定考试目标，再开始今天的学习。",
            "assignments": student_assignments(db, user),
        }
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)
    tasks = db.scalars(
        select(Task).where(Task.user_id == user.id, Task.goal_id == goal.id, Task.day == today, Task.status != "skipped")
    ).all()
    lesson_done = any(
        task.status == "done" and task.type not in ("practice", "quiz", "review", "speech")
        for task in tasks
    )
    quiz_done = (
        db.scalar(
            select(func.count(QuizAttempt.id)).where(
                QuizAttempt.user_id == user.id,
                QuizAttempt.goal_id == goal.id,
                QuizAttempt.created_at >= start,
                QuizAttempt.created_at < end,
            )
        )
        or 0
    ) > 0
    voice_done = False
    session_ids = db.scalars(select(CoachSession.id).where(CoachSession.user_id == user.id)).all()
    if session_ids:
        voice_done = (
            db.scalar(
                select(func.count(CoachMessage.id)).where(
                    CoachMessage.session_id.in_(session_ids),
                    CoachMessage.role == "user",
                    CoachMessage.created_at >= start,
                    CoachMessage.created_at < end,
                )
            )
            or 0
        ) > 0
    review_done = (
        db.scalar(
            select(DailyReview.id).where(
                DailyReview.user_id == user.id,
                DailyReview.goal_id == goal.id,
                DailyReview.day == today,
            )
        )
        is not None
    )
    steps = [
        {"key": "lesson", "label": "看课", "done": lesson_done, "hint": "先完成今天安排里的学习任务"},
        {"key": "quiz", "label": "随堂测", "done": quiz_done, "hint": "对着刚才的知识点做一组题"},
        {"key": "voice", "label": "口语与追问", "done": voice_done, "hint": "跟读后向教练复述，或追问错在哪里"},
        {"key": "review", "label": "复盘", "done": review_done, "hint": "记下今天的难点和下一步"},
    ]
    pending = next((step for step in steps if not step["done"]), None)
    week = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        done = db.scalar(
            select(func.count(Task.id)).where(
                Task.user_id == user.id,
                Task.goal_id == goal.id,
                Task.day == day,
                Task.status == "done",
            )
        ) or 0
        week.append({"day": day, "done": int(done)})
    return {
        "loop_steps": steps,
        "week_activity": week,
        "next_step": pending["hint"] if pending else "今天的四步都已留下记录。",
        "assignments": student_assignments(db, user),
    }


def close_coaching(db: Session, user: User, session: CoachSession) -> dict:
    rows = db.scalars(
        select(CoachMessage).where(CoachMessage.session_id == session.id).order_by(CoachMessage.id.asc())
    ).all()
    if not rows:
        raise ValueError("还没有对话，先问一个问题再结束")
    questions = [row.text.strip() for row in rows if row.role == "user" and row.text.strip()]
    replies = [row.text.strip() for row in rows if row.role == "coach" and row.text.strip()]
    takeaways: List[str] = []
    if questions:
        takeaways.append(f"这次围绕「{questions[0][:36]}」")
    if replies:
        brief = replies[-1].replace("\n", " ")
        takeaways.append(brief[:48] + ("…" if len(brief) > 48 else ""))
    if len(questions) > 1:
        takeaways.append(f"还追问了「{questions[-1][:24]}」")
    if len(takeaways) < 2:
        takeaways.append("先把今天还没完成的任务做完。")
    takeaways = takeaways[:3]
    next_practice = "回到今日，补上还没完成的一环；刚标出的难点可以在闪卡里复习。"
    payload = {"takeaways": takeaways, "next_practice": next_practice}
    session.closing = json.dumps(payload, ensure_ascii=False)
    session.updated_at = datetime.utcnow()
    db.commit()
    return {"session_id": session.id, "title": session.title, **payload}


def student_assignments(db: Session, user: User) -> List[dict]:
    class_ids = db.scalars(select(ClassMember.class_id).where(ClassMember.user_id == user.id)).all()
    if not class_ids:
        return []
    rows = db.scalars(
        select(ClassAssignment).where(ClassAssignment.class_id.in_(class_ids)).order_by(ClassAssignment.id.desc())
    ).all()
    briefs = []
    for row in rows[:5]:
        package = db.scalar(select(SkillPackage).where(SkillPackage.slug == row.package_slug))
        name = package.name if package else row.title
        briefs.append(
            {
                "id": row.id,
                "title": row.title,
                "package_name": name,
                "hint": f"教师布置了「{name}」，可在学科包中导入后按今天的任务练习。",
            }
        )
    return briefs


def assign_package(db: Session, user: User, school_class: SchoolClass, slug: str) -> dict:
    ensure_packages(db)
    db.commit()
    package = db.scalar(select(SkillPackage).where(SkillPackage.slug == slug))
    if package is None or (package.status or "approved") != "approved":
        raise ValueError("只能布置已通过审核的学科包")
    if not package.official and not package.shared:
        raise ValueError("这个学科包还没有分享，不能布置给班级")
    row = ClassAssignment(
        class_id=school_class.id,
        package_slug=package.slug,
        title=package.name,
        created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return assignment_progress(db, school_class, row, package)


def assignment_progress(db: Session, school_class: SchoolClass, row: ClassAssignment, package: Optional[SkillPackage] = None) -> dict:
    package = package or db.scalar(select(SkillPackage).where(SkillPackage.slug == row.package_slug))
    try:
        points = json.loads(package.config).get("points", []) if package else []
    except Exception:
        points = []
    names = {str(item.get("name") or "").strip().lower() for item in points if item.get("name")}
    members = class_members(db, school_class.id)
    started = 0
    for member in members:
        goal = db.scalar(select(Goal).where(Goal.user_id == member.id).order_by(Goal.created_at.desc()))
        if goal is None or not names:
            continue
        owned = db.scalars(select(KnowledgePoint.name).where(KnowledgePoint.goal_id == goal.id)).all()
        if names.intersection({item.lower() for item in owned}):
            started += 1
    total = len(members)
    return {
        "id": row.id,
        "class_id": school_class.id,
        "slug": row.package_slug,
        "title": row.title,
        "member_count": total,
        "started": started,
        "completion_rate": round(started / total, 3) if total else 0.0,
        "detail": "完成度按已导入该学科包知识点的学生计算。",
    }


def list_assignments(db: Session, school_class: SchoolClass) -> List[dict]:
    rows = db.scalars(
        select(ClassAssignment).where(ClassAssignment.class_id == school_class.id).order_by(ClassAssignment.id.desc())
    ).all()
    return [assignment_progress(db, school_class, row) for row in rows]
