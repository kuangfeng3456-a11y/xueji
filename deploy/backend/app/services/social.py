"""班级 / 教师看板与学习搭子的聚合统计。"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ClassMember,
    Goal,
    KnowledgePoint,
    Mastery,
    SchoolClass,
    Task,
    User,
)
from .rules import calc_streak, completion_rate, days_left


def member_profile(db: Session, member: User, today: Optional[date] = None) -> Dict:
    """单个成员的学习画像：连续打卡、本周完成率、平均掌握度、最薄弱点。"""
    today = today or date.today()
    goal = db.scalar(
        select(Goal).where(Goal.user_id == member.id).order_by(Goal.created_at.desc()).limit(1)
    )
    profile = {
        "user_id": member.id,
        "username": member.username,
        "nickname": member.nickname,
        "school": member.school,
        "goal_name": goal.exam_name if goal else None,
        "days_left": days_left(goal.exam_date, today) if goal else None,
        "streak": 0,
        "completion_rate": 0.0,
        "avg_mastery": 0.0,
        "weakest": None,
        "tasks_7d": 0,
        "done_7d": 0,
    }
    if goal is None:
        return profile

    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_map = {point.id: point for point in points}
    mastery_rows = (
        db.scalars(
            select(Mastery).where(
                Mastery.user_id == member.id,
                Mastery.kp_id.in_([point.id for point in points] or [0]),
            )
        ).all()
        if points
        else []
    )
    mastery_map = {row.kp_id: row.value for row in mastery_rows}
    if mastery_rows:
        profile["avg_mastery"] = round(sum(row.value for row in mastery_rows) / len(mastery_rows), 3)
        weakest_id = min(mastery_map, key=mastery_map.get)
        profile["weakest"] = point_map.get(weakest_id).name if weakest_id in point_map else None

    week_start = today - timedelta(days=6)
    week_tasks = db.scalars(
        select(Task).where(
            Task.user_id == member.id,
            Task.goal_id == goal.id,
            Task.day >= week_start,
            Task.day <= today,
        )
    ).all()
    judged = [task for task in week_tasks if task.status != "skipped"]
    done = [task for task in judged if task.status == "done"]
    profile["completion_rate"] = completion_rate(len(done), len(judged))
    profile["tasks_7d"] = len(judged)
    profile["done_7d"] = len(done)

    done_days = {
        task.day
        for task in db.scalars(
            select(Task).where(
                Task.user_id == member.id,
                Task.goal_id == goal.id,
                Task.status == "done",
            )
        ).all()
    }
    profile["streak"] = calc_streak(done_days, today)
    return profile


def class_members(db: Session, class_id: int) -> List[User]:
    rows = db.scalars(select(ClassMember).where(ClassMember.class_id == class_id)).all()
    user_ids = [row.user_id for row in rows]
    if not user_ids:
        return []
    return list(db.scalars(select(User).where(User.id.in_(user_ids))).all())


def build_class_dashboard(
    db: Session, school_class: SchoolClass, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    members = class_members(db, school_class.id)
    member_ids = [member.id for member in members]

    goals = (
        db.scalars(
            select(Goal)
            .where(Goal.user_id.in_(member_ids))
            .order_by(Goal.created_at.desc())
        ).all()
        if member_ids
        else []
    )
    goal_by_user: Dict[int, Goal] = {}
    for goal in goals:
        goal_by_user.setdefault(goal.user_id, goal)
    goal_ids = list({goal.id for goal in goal_by_user.values()})

    points = (
        db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id.in_(goal_ids))).all()
        if goal_ids
        else []
    )
    point_map = {point.id: point for point in points}
    point_ids = list(point_map)

    mastery_rows = (
        db.scalars(
            select(Mastery).where(
                Mastery.user_id.in_(member_ids), Mastery.kp_id.in_(point_ids)
            )
        ).all()
        if member_ids and point_ids
        else []
    )
    mastery_by_user: Dict[int, List[Mastery]] = defaultdict(list)
    for row in mastery_rows:
        point = point_map.get(row.kp_id)
        goal = goal_by_user.get(row.user_id)
        if point and goal and point.goal_id == goal.id:
            mastery_by_user[row.user_id].append(row)

    week_start = today - timedelta(days=6)
    week_tasks = (
        db.scalars(
            select(Task).where(
                Task.user_id.in_(member_ids),
                Task.day >= week_start,
                Task.day <= today,
            )
        ).all()
        if member_ids
        else []
    )
    tasks_by_user: Dict[int, List[Task]] = defaultdict(list)
    for task in week_tasks:
        goal = goal_by_user.get(task.user_id)
        if goal and task.goal_id == goal.id:
            tasks_by_user[task.user_id].append(task)

    done_rows = (
        db.execute(
            select(Task.user_id, Task.day).where(
                Task.user_id.in_(member_ids), Task.status == "done"
            )
        ).all()
        if member_ids
        else []
    )
    done_days_by_user: Dict[int, set] = defaultdict(set)
    for user_id, day in done_rows:
        done_days_by_user[user_id].add(day)

    mastery_by_name: Dict[str, List[float]] = defaultdict(list)
    profiles = []
    for member in members:
        goal = goal_by_user.get(member.id)
        profile = {
            "user_id": member.id,
            "username": member.username,
            "nickname": member.nickname,
            "school": member.school,
            "goal_name": goal.exam_name if goal else None,
            "days_left": days_left(goal.exam_date, today) if goal else None,
            "streak": 0,
            "completion_rate": 0.0,
            "avg_mastery": 0.0,
            "weakest": None,
            "tasks_7d": 0,
            "done_7d": 0,
        }

        rows = mastery_by_user.get(member.id, [])
        if rows:
            values = {row.kp_id: row.value for row in rows}
            profile["avg_mastery"] = round(sum(values.values()) / len(values), 3)
            weakest_id = min(values, key=values.get)
            weakest_point = point_map.get(weakest_id)
            profile["weakest"] = weakest_point.name if weakest_point else None
            for kp_id, value in values.items():
                point = point_map.get(kp_id)
                if point:
                    mastery_by_name[point.name].append(value)

        week = tasks_by_user.get(member.id, [])
        judged = [task for task in week if task.status != "skipped"]
        done = [task for task in judged if task.status == "done"]
        profile["completion_rate"] = completion_rate(len(done), len(judged))
        profile["tasks_7d"] = len(judged)
        profile["done_7d"] = len(done)
        profile["streak"] = calc_streak(done_days_by_user.get(member.id, set()), today)
        profiles.append(profile)

    weak_points = [
        {
            "name": name,
            "value": round(sum(values) / len(values), 3),
            "sample_count": len(values),
        }
        for name, values in mastery_by_name.items()
    ]
    weak_points.sort(key=lambda item: (item["value"], -item["sample_count"]))
    weak_points = weak_points[:6]

    rated = [profile for profile in profiles if profile["tasks_7d"] > 0]
    mastery_profiles = [profile for profile in profiles if profile["avg_mastery"] > 0]
    avg_mastery = (
        round(sum(profile["avg_mastery"] for profile in mastery_profiles) / len(mastery_profiles), 3)
        if mastery_profiles
        else 0.0
    )
    avg_completion = (
        round(sum(profile["completion_rate"] for profile in rated) / len(rated), 3) if rated else 0.0
    )
    profiles.sort(key=lambda item: (-item["streak"], -item["completion_rate"], -item["avg_mastery"]))

    return {
        "class_info": {
            "id": school_class.id,
            "name": school_class.name,
            "description": school_class.description,
            "invite_code": school_class.invite_code,
            "owner_id": school_class.owner_id,
        },
        "member_count": len(profiles),
        "active_members": sum(1 for profile in profiles if profile["streak"] > 0),
        "avg_mastery": avg_mastery,
        "avg_completion": avg_completion,
        "weak_points": weak_points,
        "members": profiles,
    }


def buddy_profiles(db: Session, user: User, today: Optional[date] = None) -> List[Dict]:
    from ..models import Buddy

    rows = db.scalars(select(Buddy).where(Buddy.user_id == user.id)).all()
    buddy_ids = [row.buddy_id for row in rows]
    buddies = list(db.scalars(select(User).where(User.id.in_(buddy_ids))).all()) if buddy_ids else []
    profiles = [member_profile(db, buddy, today) for buddy in buddies]
    me = member_profile(db, user, today)
    me["is_me"] = True
    for profile in profiles:
        profile["is_me"] = False
    profiles.append(me)
    profiles.sort(key=lambda item: (-item["streak"], -item["completion_rate"], -item["avg_mastery"]))
    return profiles