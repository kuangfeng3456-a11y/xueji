"""教师教学决策台：班级聚合薄弱点、共性错因与分层建议。"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, Mistake, Task
from .rules import MISTAKE_CATEGORIES, completion_rate
from .social import class_members


def teacher_dashboard(db: Session, school_class, today: date = None) -> Dict:
    today = today or date.today()
    members = class_members(db, school_class.id)
    member_ids = [member.id for member in members]
    name_map = {member.id: (member.nickname or member.username) for member in members}

    goals = (
        db.scalars(
            select(Goal).where(Goal.user_id.in_(member_ids)).order_by(Goal.created_at.desc())
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
    rows = (
        db.scalars(
            select(Mastery).where(
                Mastery.user_id.in_(member_ids), Mastery.kp_id.in_(list(point_map) or [0])
            )
        ).all()
        if member_ids and point_map
        else []
    )
    agg: Dict[int, List[float]] = defaultdict(list)
    per_member: Dict[int, List[float]] = defaultdict(list)
    for row in rows:
        point = point_map.get(row.kp_id)
        goal = goal_by_user.get(row.user_id)
        if point and goal and point.goal_id == goal.id:
            agg[row.kp_id].append(row.value)
            per_member[row.user_id].append(row.value)

    weak_points = sorted(
        [
            {
                "kp_id": kp_id,
                "name": point_map[kp_id].name,
                "avg_mastery": round(sum(values) / len(values), 3),
                "students": len(values),
            }
            for kp_id, values in agg.items()
        ],
        key=lambda item: item["avg_mastery"],
    )[:5]

    mistakes = (
        db.scalars(select(Mistake).where(Mistake.user_id.in_(member_ids))).all()
        if member_ids
        else []
    )
    distribution: Dict[str, int] = defaultdict(int)
    for mistake in mistakes:
        distribution[mistake.category] += 1
    common_errors = [
        {"category": key, "label": label, "count": distribution.get(key, 0)}
        for key, label in MISTAKE_CATEGORIES.items()
    ]

    member_avg = {
        user_id: round(sum(values) / len(values), 3)
        for user_id, values in per_member.items()
        if values
    }
    tiers = {
        "high": [uid for uid, value in member_avg.items() if value >= 0.7],
        "mid": [uid for uid, value in member_avg.items() if 0.4 <= value < 0.7],
        "low": [uid for uid, value in member_avg.items() if value < 0.4],
    }
    watch_list = [
        {"user_id": uid, "name": name_map.get(uid, ""), "avg_mastery": member_avg[uid]}
        for uid in tiers["low"]
    ]

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
    judged = [task for task in week_tasks if task.status != "skipped"]
    done = [task for task in judged if task.status == "done"]
    rate = completion_rate(len(done), len(judged))

    suggestions = []
    if weak_points:
        suggestions.append(f"建议先集体讲解「{weak_points[0]['name']}」，再进行分层练习。")
    if common_errors:
        top = max(common_errors, key=lambda item: item["count"])
        if top["count"]:
            suggestions.append(f"共性错因集中在「{top['label']}」，可安排一次针对性纠错。")
    if watch_list:
        suggestions.append(f"{len(watch_list)} 名学生需人工关注，建议课后单独沟通。")
    if not suggestions:
        suggestions.append("当前班级数据较少，建议先完成一次诊断练习。")

    flat = [value for values in per_member.values() for value in values]
    avg_mastery = round(sum(flat) / len(flat), 3) if flat else 0.0

    return {
        "class_id": school_class.id,
        "class_name": school_class.name,
        "owner_id": school_class.owner_id,
        "member_count": len(members),
        "weak_points": weak_points,
        "common_errors": common_errors,
        "tiers": {key: len(value) for key, value in tiers.items()},
        "tier_members": {
            key: [name_map.get(uid, "") for uid in value] for key, value in tiers.items()
        },
        "watch_list": watch_list,
        "completion_rate": rate,
        "avg_mastery": avg_mastery,
        "suggestions": suggestions,
        "note": "仅展示授权班级的聚合数据；个体名单仅班级创建者可见。",
    }