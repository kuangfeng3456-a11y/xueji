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
    Mastery,
    QuizAttempt,
    Report,
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
    steered = steer_today(
        db,
        user,
        goal,
        point,
        f"「{point.name}」刚被标成需要复习，今天先补这一处。",
    )
    return {
        "kp_id": point.id,
        "name": point.name,
        "next_review_at": today.isoformat(),
        "review_stage": record.review_stage,
        "task_id": steered["task_id"],
        "detail": steered["detail"] + "复习间隔没有被改写。",
    }


def steer_today(db: Session, user: User, goal: Goal, point: KnowledgePoint, reason: str, today: Optional[date] = None) -> dict:
    """把刚暴露的弱项排进今天还没做的任务。已有补练则提高优先级，没有就插入一条。"""
    today = today or date.today()
    pending = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.kp_id == point.id,
            Task.day == today,
            Task.status == "pending",
            Task.type.in_(("remedial", "practice", "review")),
        )
    ).all()
    if pending:
        task = max(pending, key=lambda item: item.priority)
        task.priority = round(max(task.priority, 5) + 1, 3)
        task.reason = (reason or task.reason)[:240]
        action = "raised"
    else:
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            day=today,
            title=f"针对弱项：{point.name}",
            type="remedial",
            duration_min=20,
            status="pending",
            reason=(reason or f"根据刚才的练习，今天优先补「{point.name}」。")[:240],
            priority=9,
            source="steer",
        )
        db.add(task)
        db.flush()
        action = "inserted"
    _fit_today(db, user.id, goal, task, today)
    db.commit()
    return {
        "task_id": task.id,
        "title": task.title,
        "kp_id": point.id,
        "kp_name": point.name,
        "action": action,
        "detail": f"今天剩下的安排已改为先做「{task.title}」。",
    }


def release_practice(db: Session, user: User, goal: Goal, point: KnowledgePoint, today: Optional[date] = None) -> dict:
    """复习通过后，把该知识点今天的补练标成完成，让它离开「需要练习」。"""
    today = today or date.today()
    rows = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.kp_id == point.id,
            Task.day == today,
            Task.status == "pending",
            Task.type.in_(("remedial", "practice")),
        )
    ).all()
    now = datetime.utcnow()
    for task in rows:
        task.status = "done"
        task.done_at = now
        task.reason = (task.reason or "") + "（这次复习已通过，移出今日补练）"
    db.commit()
    record = db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id))
    return {
        "cleared": len(rows),
        "kp_name": point.name,
        "mastery": record.value if record else None,
        "next_review_at": record.next_review_at.isoformat() if record and record.next_review_at else None,
    }


def _fit_today(db: Session, user_id: int, goal: Goal, kept: Task, today: date) -> None:
    pending = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        )
    ).all()
    used = sum(task.duration_min for task in pending)
    while used > goal.daily_minutes:
        movable = [task for task in pending if task.id != kept.id and task.type != "remedial"]
        if not movable:
            break
        victim = min(movable, key=lambda task: task.priority)
        victim.day = today + timedelta(days=1)
        victim.reason = (victim.reason or "") + "（今天要先补弱项，本任务改到明天）"
        pending.remove(victim)
        used -= victim.duration_min


def _weakest_point(db: Session, user: User, goal: Goal) -> Optional[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    if not points:
        return None
    best = None
    best_value = 2.0
    for point in points:
        record = db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id))
        value = record.value if record else 0.0
        if value < best_value:
            best = point
            best_value = value
    return best if best_value < 0.7 else None


def _weakest_name(db: Session, user: User, goal: Goal) -> str:
    point = _weakest_point(db, user, goal)
    return point.name if point else ""


def _weak_names(db: Session, user: User, goal: Goal) -> List[str]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    ranked = []
    for point in points:
        record = db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id))
        value = record.value if record else 0.0
        if value < 0.5:
            ranked.append((value, point.name))
    ranked.sort()
    return [name for _, name in ranked[:3]]


def _focus_task(db: Session, user: User, goal: Goal, today: date) -> Optional[Task]:
    rows = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
            Task.type == "remedial",
        ).order_by(Task.priority.desc())
    ).all()
    return rows[0] if rows else None


def _point_from_transcript(db: Session, goal: Goal, text: str) -> Optional[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    found = [point for point in points if point.name and point.name in text]
    if not found:
        return None
    return max(found, key=lambda point: len(point.name))


def ensure_assignment_tasks(db: Session, user: User, goal: Goal, today: date) -> None:
    class_ids = db.scalars(select(ClassMember.class_id).where(ClassMember.user_id == user.id)).all()
    if not class_ids:
        return
    rows = db.scalars(select(ClassAssignment).where(ClassAssignment.class_id.in_(class_ids))).all()
    for row in rows:
        source = f"assignment:{row.id}"
        existing = db.scalar(
            select(Task).where(
                Task.user_id == user.id,
                Task.goal_id == goal.id,
                Task.source == source,
            )
        )
        if existing:
            continue
        db.add(
            Task(
                user_id=user.id,
                goal_id=goal.id,
                day=today,
                title=f"教师布置：{row.title}",
                type="study",
                duration_min=20,
                status="pending",
                reason=f"教师布置了「{row.title}」。导入学科包后，按其中的知识点完成练习。",
                priority=6,
                source=source,
            )
        )
    db.commit()


def loop_status(db: Session, user: User, goal: Optional[Goal], today: Optional[date] = None) -> dict:
    today = today or date.today()
    if goal is None:
        return {
            "loop_steps": [],
            "week_activity": [],
            "next_step": "先设定考试目标，再开始今天的学习。",
            "today_digest": {
                "practiced": [],
                "still_weak": [],
                "next_practice": "先设定考试目标，再开始今天的学习。",
            },
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
        or db.scalar(
            select(Report.id).where(
                Report.user_id == user.id,
                Report.goal_id == goal.id,
                Report.created_at >= start,
                Report.created_at < end,
            )
        )
        is not None
    )
    ensure_assignment_tasks(db, user, goal, today)
    tasks = db.scalars(
        select(Task).where(Task.user_id == user.id, Task.goal_id == goal.id, Task.day == today, Task.status != "skipped")
    ).all()
    steps = [
        {"key": "lesson", "label": "看课", "done": lesson_done, "hint": "先完成今天安排里的学习任务"},
        {"key": "quiz", "label": "随堂测", "done": quiz_done, "hint": "对着刚才的知识点做一组题"},
        {"key": "voice", "label": "口语与追问", "done": voice_done, "hint": "跟读后向教练复述，或追问错在哪里"},
        {"key": "review", "label": "复盘", "done": review_done, "hint": "记下今天的难点和下一步"},
    ]
    focus = _focus_task(db, user, goal, today)
    pending = next((step for step in steps if not step["done"]), None)
    if focus:
        next_step = f"先完成「{focus.title}」。这是根据当前弱项排进今天的。"
    elif pending:
        weak_name = _weakest_name(db, user, goal)
        next_step = pending["hint"] + (f"当前最需要练的是「{weak_name}」。" if weak_name else "")
    else:
        next_step = "今天的四步都已留下记录。"
    practiced = [task.title for task in tasks if task.status == "done"][:5]
    still_weak = _weak_names(db, user, goal)
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
        "next_step": next_step,
        "today_digest": {
            "practiced": practiced,
            "still_weak": still_weak,
            "next_practice": next_step,
        },
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
    next_practice = "回到今日，补上还没完成的一环。"
    if session.goal_id:
        goal = db.get(Goal, session.goal_id)
        point = _point_from_transcript(db, goal, " ".join(questions + replies)) if goal else None
        if point is None and goal:
            point = _weakest_point(db, user, goal)
        if point and goal:
            steered = steer_today(db, user, goal, point, f"教练这次围绕「{point.name}」，今天接着练它。")
            next_practice = steered["detail"]
            db.refresh(session)
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
    finished = 0
    for member in members:
        done = db.scalar(
            select(Task.id).where(
                Task.user_id == member.id,
                Task.source == f"assignment:{row.id}",
                Task.status == "done",
            )
        )
        if done:
            finished += 1
            continue
        if names:
            goal = db.scalar(select(Goal).where(Goal.user_id == member.id).order_by(Goal.created_at.desc()))
            if goal is None:
                continue
            point_ids = [
                item.id
                for item in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
                if item.name and item.name.lower() in names
            ]
            if point_ids and db.scalar(
                select(Task.id).where(
                    Task.user_id == member.id,
                    Task.kp_id.in_(point_ids),
                    Task.status == "done",
                    Task.created_at >= row.created_at,
                )
            ):
                finished += 1
    return {
        "id": row.id,
        "class_id": school_class.id,
        "slug": row.package_slug,
        "title": row.title,
        "member_count": total,
        "started": started,
        "finished": finished,
        "completion_rate": round(finished / total, 3) if total else 0.0,
        "detail": "完成度按已做完本次布置、或已练过包内知识点的学生计算。",
    }


def list_assignments(db: Session, school_class: SchoolClass) -> List[dict]:
    rows = db.scalars(
        select(ClassAssignment).where(ClassAssignment.class_id == school_class.id).order_by(ClassAssignment.id.desc())
    ).all()
    return [assignment_progress(db, school_class, row) for row in rows]
