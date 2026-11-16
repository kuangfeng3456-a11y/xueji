"""准备度、备考风险识别与风险救援。"""

import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Goal,
    KnowledgeGap,
    KnowledgePoint,
    Mastery,
    ReplanLog,
    Task,
    User,
    Violation,
)
from .rules import clamp, days_left
from .knowledge_map import _mistake_counts


def _mastery_points(db: Session, user_id: int, goal_id: int) -> Tuple[List[KnowledgePoint], Dict[int, float]]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    return points, {row.kp_id: row.value for row in rows}


def compute_readiness(
    db: Session, user: User, goal: Goal, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    points, mastery = _mastery_points(db, user.id, goal.id)
    total_weight = sum(max(point.weight, 0.1) for point in points)
    coverage = (
        sum(max(point.weight, 0.1) * mastery.get(point.id, 0.0) for point in points)
        / total_weight
        if total_weight
        else 0.0
    )

    pending = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day >= today,
        )
    ).all()
    load_minutes = sum(task.duration_min for task in pending)
    today_pending = [task for task in pending if task.day == today]
    today_minutes = sum(task.duration_min for task in today_pending)
    today_tasks = len(today_pending)
    remaining = max((goal.exam_date - today).days, 1)
    available = max(1, remaining * goal.daily_minutes)
    load_ratio = load_minutes / available

    overdue = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day < today,
        )
    ).all()
    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id,
            KnowledgeGap.goal_id == goal.id,
            KnowledgeGap.status == "verified",
        )
    ).all()
    violations = db.scalars(
        select(Violation).where(
            Violation.user_id == user.id,
            Violation.goal_id == goal.id,
            Violation.day >= today - timedelta(days=6),
        )
    ).all()

    required_minutes = max(1, load_minutes)
    time_fit = min(1.0, available / required_minutes)
    penalty = min(15, 3 * len(gaps) + 1 * len(overdue) + 2 * len(violations))
    # 文档 5.6：Ready = 100 × Coverage × (0.7 + 0.3·TimeFit) − Penalty
    score = 100 * coverage * (0.7 + 0.3 * time_fit) - penalty
    score = int(round(clamp(score, 0, 100)))
    if score >= 80:
        level = "excellent"
    elif score >= 60:
        level = "good"
    elif score >= 40:
        level = "risk"
    else:
        level = "critical"

    factors = [
        f"高权重覆盖度 {round(coverage * 100)}%",
        f"时间匹配度 {round(time_fit * 100)}%（待完成 {load_minutes} 分钟 / 可用 {available} 分钟）",
    ]
    if gaps:
        factors.append(f"已验证漏洞 {len(gaps)} 个")
    if overdue:
        factors.append(f"逾期任务 {len(overdue)} 个")
    if violations:
        factors.append(f"近 7 天违约 {len(violations)} 次")
    if penalty:
        factors.append(f"扣分 {penalty} 分（漏洞 / 逾期 / 违约）")

    return {
        "score": score,
        "level": level,
        "coverage": round(coverage, 4),
        "time_fit": round(time_fit, 4),
        "penalty": penalty,
        "load_ratio": round(load_ratio, 4),
        "gap_count": len(gaps),
        "today_tasks": today_tasks,
        "today_minutes": today_minutes,
        "formula": "Ready = 100 × Coverage × (0.7 + 0.3·TimeFit) − Penalty；Penalty = min(15, 3·漏洞 + 逾期 + 2·违约)",
        "factors": factors,
    }


def build_risks(
    db: Session,
    user: User,
    goal: Goal,
    today: Optional[date] = None,
    readiness: Optional[Dict] = None,
) -> List[Dict]:
    today = today or date.today()
    if readiness is None:
        readiness = compute_readiness(db, user, goal, today)
    points, mastery = _mastery_points(db, user.id, goal.id)
    mistakes = _mistake_counts(db, user.id, goal.id)
    risks: List[Dict] = []

    weak_weighted = [
        point
        for point in points
        if point.weight >= 1.5 and mastery.get(point.id, 0.0) < 0.4
    ]
    verified_gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id,
            KnowledgeGap.goal_id == goal.id,
            KnowledgeGap.status == "verified",
        )
    ).all()
    if weak_weighted or verified_gaps:
        high = len(verified_gaps) >= 2 or len(weak_weighted) >= 2
        risks.append(
            {
                "code": "knowledge",
                "title": "知识风险",
                "level": "high" if high else "medium",
                "reason": (
                    f"已验证漏洞 {len(verified_gaps)} 个，"
                    f"高权重薄弱知识点 {len(weak_weighted)} 个"
                ),
                "suggestion": "优先修复高权重薄弱点，生成修复任务并做验证题确认。",
                "before": f"准备度 {readiness['score']}%",
                "after": f"预计提升 {min(20, len(verified_gaps) * 6 + len(weak_weighted) * 3)} 个百分点",
                "action": "生成修复任务",
            }
        )

    if readiness["load_ratio"] > 1.0:
        risks.append(
            {
                "code": "time",
                "title": "时间风险",
                "level": "high" if readiness["load_ratio"] > 1.3 else "medium",
                "reason": f"待完成任务负荷是剩余可用时间的 {round(readiness['load_ratio'] * 100)}%",
                "suggestion": "压缩低优先级任务，把关键任务重排到最近的高精力时段。",
                "before": f"负荷 {round(readiness['load_ratio'] * 100)}%",
                "after": "预计降到 85% 以内",
                "action": "一键压缩与重排",
            }
        )

    overdue = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day < today,
        )
    ).all()
    if len(overdue) >= 2:
        risks.append(
            {
                "code": "execution",
                "title": "执行风险",
                "level": "high" if len(overdue) >= 4 else "medium",
                "reason": f"已有 {len(overdue)} 个任务逾期未完成",
                "suggestion": "降低今日任务颗粒度，先完成 1 个最小任务恢复节奏。",
                "before": f"逾期 {len(overdue)} 个",
                "after": "保留 1 个最小任务，其余顺延",
                "action": "颗粒度降载",
            }
        )

    due_reviews = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
            Mastery.next_review_at <= today,
        )
    ).all()
    if len(due_reviews) >= 5:
        risks.append(
            {
                "code": "memory",
                "title": "记忆风险",
                "level": "medium",
                "reason": f"有 {len(due_reviews)} 个知识点已到复习时间",
                "suggestion": "插入 1 个复习任务，优先回顾到期且掌握度低于 0.5 的知识点。",
                "before": f"到期 {len(due_reviews)} 个",
                "after": "插入 15 分钟复习任务",
                "action": "插入复习任务",
            }
        )

    if not any(mistakes.values()) and not verified_gaps:
        risks.append(
            {
                "code": "strategy",
                "title": "策略风险",
                "level": "low",
                "reason": "还没有足够数据判断哪种学习方式对你最有效",
                "suggestion": "在策略实验室做一次 3 天小实验，比较精读、刷题与闪卡的收益。",
                "before": "策略偏好未知",
                "after": "获得策略收益基线",
                "action": "去策略实验室",
            }
        )
    return risks


def _rest_today(db: Session, user: User, goal: Goal, today: date) -> Tuple[int, List[Dict]]:
    pending = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        ).order_by(Task.priority.desc())
    ).all()
    if len(pending) <= 1:
        return 0, [{"kind": "keep", "detail": "今日任务已足够精简", "task_id": None}]
    changes = []
    kept = pending[0]
    moved = 0
    for task in pending[1:]:
        target = today + timedelta(days=1)
        latest = goal.exam_date - timedelta(days=1)
        if target > latest:
            task.status = "skipped"
        else:
            task.day = target
            task.reason = task.reason + "（风险救援：疲劳与负荷降载，自动顺延）"
            moved += 1
        changes.append(
            {
                "kind": "defer",
                "detail": f"「{task.title}」顺延到 {target.isoformat()}",
                "task_id": task.id,
            }
        )
    db.add(
        ReplanLog(
            user_id=user.id,
            goal_id=goal.id,
            trigger="risk_rest",
            changes=json.dumps(changes, ensure_ascii=False),
        )
    )
    db.commit()
    return moved, changes


def resolve_risk(
    db: Session, user: User, goal: Goal, code: str, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    before = compute_readiness(db, user, goal, today)
    changes: List[Dict] = []
    message = ""

    if code in ("time", "execution"):
        moved, changes = _rest_today(db, user, goal, today)
        message = f"已降载：顺延 {moved} 个任务，保留 1 个最高优先级任务。"
    elif code == "knowledge":
        points, mastery = _mastery_points(db, user.id, goal.id)
        weakest = sorted(
            [point for point in points if point.weight >= 1.0],
            key=lambda point: mastery.get(point.id, 0.0),
        )[:2]
        for point in weakest:
            db.add(
                Task(
                    user_id=user.id,
                    goal_id=goal.id,
                    kp_id=point.id,
                    day=today,
                    title=f"漏洞修复：{point.name}",
                    type="remedial",
                    duration_min=20,
                    status="pending",
                    reason="风险救援：高权重薄弱知识点优先修复，完成后用验证题确认。",
                    priority=3.5,
                    source="risk",
                )
            )
        db.add(
            ReplanLog(
                user_id=user.id,
                goal_id=goal.id,
                trigger="risk_knowledge",
                changes=json.dumps(
                    [{"kind": "repair", "detail": "生成漏洞修复任务", "task_id": None}],
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        message = f"已生成 {len(weakest)} 个漏洞修复任务，完成后请做验证题确认。"
        changes = [
            {"kind": "repair", "detail": f"生成修复任务：{point.name}", "task_id": None}
            for point in weakest
        ]
    elif code == "memory":
        points, mastery = _mastery_points(db, user.id, goal.id)
        ordered = sorted(points, key=lambda point: mastery.get(point.id, 0.0))[:1]
        for point in ordered:
            db.add(
                Task(
                    user_id=user.id,
                    goal_id=goal.id,
                    kp_id=point.id,
                    day=today,
                    title=f"复习：{point.name}",
                    type="review",
                    duration_min=15,
                    status="pending",
                    reason="风险救援：记忆到期，插入针对性复习。",
                    priority=3.0,
                    source="risk",
                )
            )
        db.commit()
        message = "已插入 15 分钟复习任务。"
        changes = [{"kind": "review", "detail": f"复习 {point.name}", "task_id": None} for point in ordered]
    else:
        message = "建议先完成一次策略实验，建立个人学习方式收益基线。"
        changes = [{"kind": "strategy", "detail": message, "task_id": None}]

    after = compute_readiness(db, user, goal, today)
    return {
        "code": code,
        "before": before,
        "after": after,
        "changes": changes,
        "message": message,
    }