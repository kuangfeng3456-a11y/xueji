"""Planner Agent 的确定性内核：生成周计划与动态重排。

大模型只负责措辞，排程、时长分配、优先级与掌握度全部由这里的规则完成。
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Goal,
    KnowledgeDependency,
    KnowledgePoint,
    LearningEvent,
    Mastery,
    Mistake,
    ReplanLog,
    Task,
    TaskVariant,
)
from .mastery_service import ensure_goal_mastery
from .rhythm import build_rhythm
from .rules import (
    TASK_TYPES,
    days_left,
    distribute_minutes,
    gate_for_prerequisites,
    mastery_uncertainty,
    plan_days_left,
    retention,
    stability_for_stage,
    task_priority,
    task_tiers,
    value_density,
)

TASKS_PER_DAY = 3
REMEDIAL_MINUTES = 20


def _mastery_map(db: Session, user_id: int, goal_id: int) -> Dict[int, Mastery]:
    rows = db.scalars(
        select(Mastery).join(KnowledgePoint, Mastery.kp_id == KnowledgePoint.id).where(
            Mastery.user_id == user_id, KnowledgePoint.goal_id == goal_id
        )
    ).all()
    return {row.kp_id: row for row in rows}


def _kp_map(db: Session, goal_id: int) -> Dict[int, KnowledgePoint]:
    rows = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    return {row.id: row for row in rows}


def _leaf_points(points: List[KnowledgePoint]) -> List[KnowledgePoint]:
    """任务只安排到叶子知识点，父节点仅用于组织知识树。"""
    parent_ids = {point.parent_id for point in points if point.parent_id is not None}
    leaves = [point for point in points if point.id not in parent_ids]
    return leaves or points


def task_to_dict(task: Task, kp_map: Dict[int, KnowledgePoint]) -> dict:
    point = kp_map.get(task.kp_id) if task.kp_id else None
    return {
        "id": task.id,
        "goal_id": task.goal_id,
        "day": task.day,
        "title": task.title,
        "type": task.type,
        "duration_min": task.duration_min,
        "status": task.status,
        "reason": task.reason,
        "priority": task.priority,
        "source": task.source,
        "kp_id": task.kp_id,
        "kp_name": point.name if point else None,
        "skip_reason": task.skip_reason,
        "feedback": task.feedback,
        "tiers": task_tiers(task.duration_min),
    }


def _reason_for(point: KnowledgePoint, mastery: float, priority: float, remain: int, kind: str) -> str:
    formula = (
        f"优先级 {priority} = 权重 {point.weight:.1f} × 未掌握 {max(1 - mastery, 0.05):.2f} "
        f"× 临近系数 {priority / max(point.weight * max(1 - mastery, 0.05), 0.0001):.2f}"
    )
    if kind == "review":
        return f"遗忘曲线到期，安排复习巩固。{formula}；距考试还剩 {remain} 天。"
    if mastery < 0.35:
        lead = "掌握度偏低，先补基础概念"
    elif mastery < 0.7:
        lead = "已懂但不够稳，用练习加深"
    else:
        lead = "掌握较好，保持手感并查漏"
    return f"{lead}（当前掌握度 {mastery:.2f}）。{formula}；距考试还剩 {remain} 天。"


def build_plan(
    db: Session,
    user_id: int,
    goal: Goal,
    days: int = 7,
    regenerate: bool = False,
    today: Optional[date] = None,
) -> dict:
    today = today or date.today()
    ensure_goal_mastery(db, user_id, goal.id)
    db.flush()

    kp_map = _kp_map(db, goal.id)
    if not kp_map:
        return {"tasks": [], "summary": "还没有知识点，请先导入学习资料。", "days": 0, "total_minutes": 0}

    if regenerate:
        existing = db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal.id,
                Task.day >= today,
                Task.status == "pending",
                Task.source == "plan",
            )
        ).all()
        for task in existing:
            # 先删三档版本，避免 SQLite 复用 task_id 时触发唯一约束
            variants = db.scalars(
                select(TaskVariant).where(TaskVariant.task_id == task.id)
            ).all()
            for variant in variants:
                db.delete(variant)
            db.delete(task)
        db.flush()

    mastery_map = _mastery_map(db, user_id, goal.id)
    event_counts = dict(
        db.execute(
            select(LearningEvent.kp_id, func.count(LearningEvent.id))
            .where(
                LearningEvent.user_id == user_id,
                LearningEvent.goal_id == goal.id,
                LearningEvent.event_type == "answer",
            )
            .group_by(LearningEvent.kp_id)
        ).all()
    )
    prereq_map: Dict[int, List[int]] = defaultdict(list)
    for dep in db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal.id)
    ).all():
        prereq_map[dep.to_kp_id].append(dep.from_kp_id)
    rhythm = build_rhythm(db, user_id, goal.id, today=today)
    tasks_per_day = rhythm["tasks_per_day"]
    existing_days = set(
        db.scalars(
            select(Task.day).where(Task.user_id == user_id, Task.goal_id == goal.id, Task.day >= today)
        ).all()
    )

    horizon = min(days, plan_days_left(goal.exam_date, today), 30)
    created: List[Task] = []
    points = _leaf_points(list(kp_map.values()))
    planned_load: Dict[int, int] = defaultdict(int)

    for offset in range(horizon):
        current_day = today + timedelta(days=offset)
        if current_day in existing_days:
            continue
        remain = days_left(goal.exam_date, current_day)

        scored: List[Tuple[KnowledgePoint, Mastery, float]] = []
        density_map: Dict[int, float] = {}
        for point in points:
            record = mastery_map.get(point.id)
            mastery = record.value if record else 0.0
            priority = task_priority(point.weight, mastery, remain)
            stability = stability_for_stage(record.review_stage if record else 0)
            last_day = record.updated_at.date() if record and record.updated_at else today
            retention_now = retention(max(0, (current_day - last_day).days), stability)
            uncertainty = mastery_uncertainty(mastery, float(event_counts.get(point.id, 0)))
            prereq_values = [
                (mastery_map.get(pid).value if mastery_map.get(pid) else 0.0)
                for pid in prereq_map.get(point.id, [])
            ]
            gate = gate_for_prerequisites(prereq_values)
            density_map[point.id] = value_density(
                point.weight, mastery, retention_now, uncertainty, remain, gate, 20
            )["density"]
            scored.append((point, record, priority))
        scored.sort(key=lambda item: density_map[item[0].id], reverse=True)
        ranked = sorted(
            scored,
            key=lambda item: density_map[item[0].id] / (1 + planned_load[item[0].id]),
            reverse=True,
        )

        due_review = [
            item
            for item in ranked
            if item[1] and item[1].next_review_at and item[1].next_review_at <= current_day
        ]
        review_item = due_review[0] if due_review else (ranked[0] if ranked and ranked[0][0].weight >= 1.0 else None)

        chosen: List[Tuple[KnowledgePoint, Mastery, float, str]] = []
        if review_item:
            point, record, priority = review_item
            chosen.append((point, record, priority, "review"))
            planned_load[point.id] += 1

        for point, record, priority in ranked:
            if len(chosen) >= tasks_per_day:
                break
            if any(item[0].id == point.id for item in chosen):
                continue
            mastery = record.value if record else 0.0
            if remain <= 1:
                kind = "review"
            elif remain <= 3:
                kind = "review" if mastery < 0.7 else "practice"
            else:
                kind = "study" if mastery < 0.35 else "practice"
            chosen.append((point, record, priority, kind))
            planned_load[point.id] += 1

        if not chosen:
            continue

        durations = distribute_minutes(goal.daily_minutes, len(chosen))
        if chosen[0][3] == "review":
            review_minutes = max(10, int(goal.daily_minutes * 0.3))
            rest = distribute_minutes(max(goal.daily_minutes - review_minutes, len(chosen) - 1), len(chosen) - 1)
            durations = [review_minutes] + rest

        for (point, record, priority, kind), minutes in zip(chosen, durations):
            mastery = record.value if record else 0.0
            task = Task(
                user_id=user_id,
                goal_id=goal.id,
                kp_id=point.id,
                day=current_day,
                title=f"{TASK_TYPES.get(kind, '学习')}：{point.name}",
                type=kind,
                duration_min=minutes,
                status="pending",
                reason=_reason_for(point, mastery, priority, remain, kind),
                priority=priority,
                source="plan",
            )
            db.add(task)
            db.flush()
            # 文档 5.4：三档任务落库，供回看、复算与前端切换
            tiers = task_tiers(task.duration_min)
            for tier, tier_minutes in tiers.items():
                db.add(
                    TaskVariant(
                        task_id=task.id,
                        tier=tier,
                        minutes=int(tier_minutes),
                        steps="",
                    )
                )
            created.append(task)

    db.flush()
    total_minutes = sum(task.duration_min for task in created)
    covered = len({task.kp_id for task in created})
    summary = (
        f"已为「{goal.exam_name}」生成 {horizon} 天、共 {len(created)} 个微任务，"
        f"覆盖 {covered} 个知识点，预计投入 {total_minutes} 分钟。"
        f"距考试 {days_left(goal.exam_date, today)} 天，每天可用 {goal.daily_minutes} 分钟。"
    )
    if tasks_per_day != TASKS_PER_DAY:
        summary += (
            f"结合最近 {rhythm['window_days']} 天完成率 {rhythm['completion_rate'] * 100:.0f}%，"
            f"每日微任务已从 {TASKS_PER_DAY} 个调整为 {tasks_per_day} 个。"
        )
    return {
        "tasks": [task_to_dict(task, kp_map) for task in created],
        "summary": summary,
        "days": horizon,
        "total_minutes": total_minutes,
    }


def _shift_task(db: Session, task: Task, target: date, goal: Goal, reason: str) -> bool:
    latest = goal.exam_date - timedelta(days=1)
    if target > latest:
        task.status = "skipped"
        task.reason = f"{task.reason}（考试临近，任务已移除）"
        return True
    task.day = target
    task.reason = reason
    db.add(task)
    return True


def _analyze_mistakes(db: Session, user_id: int, goal_id: int, today: date) -> List[dict]:
    since = today - timedelta(days=7)
    rows = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user_id,
            Mistake.goal_id == goal_id,
            Mistake.created_at >= datetime.combine(since, datetime.min.time()),
        )
    ).all()
    grouped: Dict[int, List[Mistake]] = defaultdict(list)
    for row in rows:
        if row.kp_id:
            grouped[row.kp_id].append(row)
    result = []
    for kp_id, items in grouped.items():
        if len(items) >= 2:
            result.append(
                {
                    "kp_id": kp_id,
                    "count": len(items),
                    "category": items[-1].category,
                    "label": items[-1].category_label,
                }
            )
    result.sort(key=lambda item: item["count"], reverse=True)
    return result


def replan(
    db: Session,
    user_id: int,
    goal: Goal,
    trigger: str = "manual",
    today: Optional[date] = None,
) -> dict:
    today = today or date.today()
    kp_map = _kp_map(db, goal.id)
    future_total = db.scalar(
        select(func.count(Task.id)).where(
            Task.user_id == user_id,
            Task.goal_id == goal.id,
            Task.day >= today,
            Task.day <= today + timedelta(days=7),
        )
    ) or 0
    changes: List[dict] = []
    latest = goal.exam_date - timedelta(days=1)

    overdue = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day < today,
        )
    ).all()
    for task in overdue:
        original = task.day
        task.day = today
        task.reason = task.reason + f"（原定 {original.isoformat()}，因未完成已自动顺延，今天优先补上）"
        changes.append(
            {
                "kind": "shift",
                "detail": f"「{task.title}」从 {original.isoformat()} 顺延到今天",
                "task_id": task.id,
            }
        )

    risk_points = _analyze_mistakes(db, user_id, goal.id, today)
    existing_remedial = {
        task.kp_id
        for task in db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal.id,
                Task.type == "remedial",
                Task.status == "pending",
                Task.day >= today,
            )
        ).all()
    }
    for risk in risk_points[:2]:
        if risk["kp_id"] in existing_remedial:
            continue
        point = kp_map.get(risk["kp_id"])
        if not point:
            continue
        record = db.scalar(
            select(Mastery).where(Mastery.user_id == user_id, Mastery.kp_id == point.id)
        )
        priority = task_priority(point.weight, record.value if record else 0.0, days_left(goal.exam_date, today))
        task = Task(
            user_id=user_id,
            goal_id=goal.id,
            kp_id=point.id,
            day=today,
            title=f"错因补救：{point.name}",
            type="remedial",
            duration_min=REMEDIAL_MINUTES,
            status="pending",
            reason=(
                f"最近 7 天该知识点错题 {risk['count']} 道，主要错因是「{risk['label']}」，"
                f"因此插入一次针对性补救。{risk['label']}的补救任务优先于普通练习。"
            ),
            priority=round(priority + 0.5, 3),
            source="replan",
        )
        db.add(task)
        db.flush()
        existing_remedial.add(point.id)
        changes.append(
            {
                "kind": "insert_remedial",
                "detail": f"「{point.name}」7 天内错 {risk['count']} 道（{risk['label']}），已插入 20 分钟补救任务",
                "task_id": task.id,
            }
        )

    if days_left(goal.exam_date, today) <= 7:
        today_tasks = db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal.id,
                Task.day == today,
                Task.status == "pending",
            )
        ).all()
        if today_tasks and not any(task.type == "review" for task in today_tasks):
            leaves = _leaf_points(list(kp_map.values()))
            candidates = sorted(leaves, key=lambda point: (lambda r: r.value if r else 0)(
                db.scalar(select(Mastery).where(Mastery.user_id == user_id, Mastery.kp_id == point.id))
            ))
            if candidates:
                point = candidates[0]
                record = db.scalar(
                    select(Mastery).where(Mastery.user_id == user_id, Mastery.kp_id == point.id)
                )
                priority = task_priority(point.weight, record.value if record else 0.0, 1)
                task = Task(
                    user_id=user_id,
                    goal_id=goal.id,
                    kp_id=point.id,
                    day=today,
                    title=f"复习：{point.name}",
                    type="review",
                    duration_min=15,
                    status="pending",
                    reason="距考试不足 7 天，系统自动提高复习密度，优先回顾最薄弱知识点。",
                    priority=round(priority + 0.3, 3),
                    source="replan",
                )
                db.add(task)
                db.flush()
                changes.append(
                    {
                        "kind": "exam_sprint",
                        "detail": f"距考试不足 7 天，新增「{point.name}」15 分钟冲刺复习",
                        "task_id": task.id,
                    }
                )

    balance_from = today
    for offset in range(0, 8):
        current_day = balance_from + timedelta(days=offset)
        if current_day > latest:
            break
        pending = db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal.id,
                Task.day == current_day,
                Task.status == "pending",
            )
        ).all()
        pending.sort(key=lambda task: task.priority, reverse=True)
        used = 0
        for task in pending:
            if used + task.duration_min <= goal.daily_minutes:
                used += task.duration_min
                continue
            target = current_day + timedelta(days=1)
            while target <= latest:
                occupied = sum(
                    item.duration_min
                    for item in db.scalars(
                        select(Task).where(
                            Task.user_id == user_id,
                            Task.goal_id == goal.id,
                            Task.day == target,
                            Task.status == "pending",
                        )
                    ).all()
                )
                if occupied + task.duration_min <= goal.daily_minutes:
                    break
                target += timedelta(days=1)
            old_day = task.day
            task.day = target
            if target > latest:
                task.status = "skipped"
                task.reason = f"{task.reason}（考试临近，已取消）"
                changes.append(
                    {
                        "kind": "drop",
                        "detail": f"「{task.title}」因时间冲突被移除",
                        "task_id": task.id,
                    }
                )
            else:
                task.reason = f"{task.reason}（今日时长已满，从 {old_day.isoformat()} 推迟到 {target.isoformat()}）"
                changes.append(
                    {
                        "kind": "defer",
                        "detail": f"「{task.title}」超出每日 {goal.daily_minutes} 分钟，推迟到 {target.isoformat()}",
                        "task_id": task.id,
                    }
                )

    if not changes:
        changes.append(
            {
                "kind": "keep",
                "detail": "当前计划与你的完成情况匹配，无需调整。",
                "task_id": None,
            }
        )

    log = ReplanLog(
        user_id=user_id,
        goal_id=goal.id,
        trigger=trigger,
        changes=json.dumps(changes, ensure_ascii=False),
    )
    db.add(log)
    db.commit()

    today_tasks = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status != "skipped",
        ).order_by(Task.priority.desc())
    ).all()
    moved = len(
        [item for item in changes if item.get("kind") in ("shift", "defer", "drop", "replace")]
    )
    disturbance = round(moved / future_total, 3) if future_total else 0.0
    return {
        "trigger": trigger,
        "changes": changes,
        "disturbance": disturbance,
        "disturbance_ok": disturbance <= 0.3,
        "disturbance_rule": "D = 被移动/删除/降档任务数 ÷ 未来 7 天任务数；自动重排要求 D ≤ 0.3，大改需用户确认",
        "tasks": [task_to_dict(task, kp_map) for task in today_tasks],
    }