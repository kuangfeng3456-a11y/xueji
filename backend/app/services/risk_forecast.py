"""知识漏洞早期预警：可复算风险分 + 因素贡献 + 证据 + 验证闭环。

风险只作为候选线索，不直接断言学生不会；验证题确认后才生成补救任务。
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Goal,
    KnowledgeGap,
    KnowledgePoint,
    Mastery,
    Mistake,
    ProbeItem,
    RiskPrediction,
    Task,
    User,
)
from .evidence import record_evidence

RISK_WEIGHTS = {
    "forget": 0.30,
    "prereq": 0.25,
    "error": 0.20,
    "transfer": 0.15,
    "overdue": 0.10,
}
FACTOR_LABELS = {
    "forget": "遗忘风险",
    "prereq": "先修依赖风险",
    "error": "近期错误率",
    "transfer": "迁移题失败率",
    "overdue": "任务逾期率",
}
DEFAULT_HIGH = 70.0
DEFAULT_MEDIUM = 45.0
MODEL_VERSION = "rule-risk-v1"
TRANSFER_KINDS = ("transfer", "challenge")


def _leaf_points(db: Session, goal_id: int) -> List[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    return [point for point in points if point.id not in parent_ids] or list(points)


def _mastery_rows(db: Session, user_id: int, goal_id: int) -> Dict[int, Mastery]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    return {row.kp_id: row for row in rows}


def _reverse_edges(db: Session, goal_id: int) -> Dict[int, List[int]]:
    from ..models import KnowledgeDependency

    reverse: Dict[int, List[int]] = defaultdict(list)
    for edge in db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal_id)
    ).all():
        reverse[edge.to_kp_id].append(edge.from_kp_id)
    return reverse


def _recent_mistakes(db: Session, user_id: int, goal_id: int, today: date) -> Dict[int, int]:
    start = datetime.combine(today - timedelta(days=7), datetime.min.time())
    rows = db.execute(
        select(Mistake.kp_id, func.count(Mistake.id))
        .where(
            Mistake.user_id == user_id,
            Mistake.goal_id == goal_id,
            Mistake.created_at >= start,
        )
        .group_by(Mistake.kp_id)
    ).all()
    return {kp_id: count for kp_id, count in rows if kp_id}


def _probe_stats(db: Session, user_id: int, goal_id: int) -> Dict[int, Dict[str, int]]:
    rows = db.scalars(
        select(ProbeItem).where(
            ProbeItem.user_id == user_id,
            ProbeItem.goal_id == goal_id,
            ProbeItem.kind.in_(TRANSFER_KINDS),
            ProbeItem.status == "answered",
        )
    ).all()
    stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"attempts": 0, "failures": 0})
    for row in rows:
        if not row.kp_id:
            continue
        stats[row.kp_id]["attempts"] += 1
        if row.correct is False:
            stats[row.kp_id]["failures"] += 1
    return stats


def _task_stats(db: Session, user_id: int, goal_id: int, today: date) -> Dict[int, Dict[str, int]]:
    rows = db.scalars(
        select(Task).where(Task.user_id == user_id, Task.goal_id == goal_id)
    ).all()
    stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"total": 0, "overdue": 0})
    for row in rows:
        if not row.kp_id:
            continue
        stats[row.kp_id]["total"] += 1
        if row.status == "skipped" or (row.status == "pending" and row.day < today):
            stats[row.kp_id]["overdue"] += 1
    return stats


def _level(score: float, high: float, medium: float) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def _prereq_chain(reverse: Dict[int, List[int]], kp_id: int, depth: int = 3) -> List[int]:
    result: List[int] = []
    frontier = [kp_id]
    for _ in range(depth):
        next_frontier = []
        for node in frontier:
            for parent in reverse.get(node, []):
                if parent not in result:
                    result.append(parent)
                    next_frontier.append(parent)
        if not next_frontier:
            break
        frontier = next_frontier
    return result


def risk_to_dict(row: RiskPrediction, point_map: Dict[int, KnowledgePoint]) -> Dict:
    point = point_map.get(row.kp_id)
    try:
        factors = json.loads(row.factors)
    except Exception:
        factors = []
    try:
        evidence = json.loads(row.evidence)
    except Exception:
        evidence = {}
    return {
        "id": row.id,
        "kp_id": row.kp_id,
        "kp_name": point.name if point else "",
        "parent": point_map.get(point.parent_id).name if point and point.parent_id and point.parent_id in point_map else None,
        "weight": round(point.weight, 2) if point else 1.0,
        "risk_score": round(row.risk_score, 1),
        "level": row.level,
        "factors": factors,
        "evidence": evidence,
        "confidence": round(row.confidence, 2),
        "sample_size": row.sample_size,
        "engine": row.engine,
        "model_version": row.model_version,
        "status": row.status,
        "updated_at": row.updated_at,
    }


def compute_risks(
    db: Session,
    user: User,
    goal: Goal,
    today: Optional[date] = None,
    high: float = DEFAULT_HIGH,
    medium: float = DEFAULT_MEDIUM,
) -> List[Dict]:
    today = today or date.today()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_map = {point.id: point for point in points}
    leaves = _leaf_points(db, goal.id)
    masteries = _mastery_rows(db, user.id, goal.id)
    recent_mistakes = _recent_mistakes(db, user.id, goal.id, today)
    probe_stats = _probe_stats(db, user.id, goal.id)
    task_stats = _task_stats(db, user.id, goal.id, today)
    reverse = _reverse_edges(db, goal.id)

    existing = {
        row.kp_id: row
        for row in db.scalars(
            select(RiskPrediction).where(
                RiskPrediction.user_id == user.id, RiskPrediction.goal_id == goal.id
            )
        ).all()
    }

    results: List[Dict] = []
    for point in leaves:
        mastery_row = masteries.get(point.id)
        mastery_value = mastery_row.value if mastery_row else 0.0
        next_review = mastery_row.next_review_at if mastery_row else None
        overdue_days = max(0, (today - next_review).days) if next_review else 7

        forget = min(100.0, (1 - mastery_value) * 70 + overdue_days * 1.6)
        chain = _prereq_chain(reverse, point.id)
        weak = [pid for pid in chain if (masteries.get(pid).value if masteries.get(pid) else 0.0) < 0.45]
        prereq = (len(weak) / len(chain) * 100) if chain else 0.0

        mistake_7d = recent_mistakes.get(point.id, 0)
        error = min(100.0, mistake_7d / 5 * 100)
        probes = probe_stats.get(point.id, {"attempts": 0, "failures": 0})
        transfer = (
            probes["failures"] / probes["attempts"] * 100 if probes["attempts"] else 0.0
        )
        tasks = task_stats.get(point.id, {"total": 0, "overdue": 0})
        overdue = tasks["overdue"] / tasks["total"] * 100 if tasks["total"] else 0.0

        factors = [
            {"key": key, "label": FACTOR_LABELS[key], "value": round(value, 1),
             "weight": RISK_WEIGHTS[key], "contribution": round(RISK_WEIGHTS[key] * value, 1)}
            for key, value in (
                ("forget", forget),
                ("prereq", prereq),
                ("error", error),
                ("transfer", transfer),
                ("overdue", overdue),
            )
        ]
        score = round(sum(item["contribution"] for item in factors), 1)
        sample_size = mistake_7d + probes["attempts"] + tasks["total"]
        confidence = min(0.95, round(0.2 + 0.06 * sample_size, 2))
        evidence = {
            "window_days": 30,
            "recent_mistakes_7d": mistake_7d,
            "probe_attempts": probes["attempts"],
            "probe_failures": probes["failures"],
            "task_total": tasks["total"],
            "task_overdue": tasks["overdue"],
            "prerequisite_weak": len(weak),
            "prerequisite_total": len(chain),
            "days_since_review": overdue_days,
            "mastery": round(mastery_value, 3),
            "data_points": sample_size,
            "insufficient": sample_size < 3,
            "calculated_at": datetime.utcnow().isoformat(),
        }
        level = _level(score, high, medium)

        row = existing.get(point.id)
        if row is None:
            row = RiskPrediction(user_id=user.id, goal_id=goal.id, kp_id=point.id)
            db.add(row)
        row.risk_score = score
        row.level = level
        row.factors = json.dumps(factors, ensure_ascii=False)
        row.evidence = json.dumps(evidence, ensure_ascii=False)
        row.confidence = confidence
        row.sample_size = sample_size
        row.engine = "rule"
        row.model_version = MODEL_VERSION
        if row.status in (None, "", "active"):
            row.status = "active"
        row.updated_at = datetime.utcnow()
        db.flush()

        record_evidence(
            db,
            user.id,
            goal.id,
            "risk_forecast",
            point.name[:60],
            {"risk_score": score, "level": level, "factors": factors, "confidence": confidence},
            f"{point.name} 风险分 {score}（{level}）",
            engine="rule",
        )
        results.append(risk_to_dict(row, point_map))

    db.commit()
    results.sort(key=lambda item: item["risk_score"], reverse=True)
    return results


def list_risks(
    db: Session,
    user: User,
    goal: Goal,
    high: float = DEFAULT_HIGH,
    medium: float = DEFAULT_MEDIUM,
) -> Dict:
    items = compute_risks(db, user, goal, high=high, medium=medium)
    active = [item for item in items if item["status"] == "active"]
    return {
        "items": items,
        "active_count": len(active),
        "high_count": len([item for item in active if item["level"] == "high"]),
        "medium_count": len([item for item in active if item["level"] == "medium"]),
        "insufficient_count": len([item for item in active if item["evidence"].get("insufficient")]),
        "thresholds": {"high": high, "medium": medium},
        "model_version": MODEL_VERSION,
        "weights": {key: RISK_WEIGHTS[key] for key in RISK_WEIGHTS},
    }


def risk_history(
    db: Session, user: User, goal: Goal, kp_id: Optional[int] = None, limit: int = 50
) -> List[Dict]:
    from ..models import Evidence

    rows = db.scalars(
        select(Evidence)
        .where(
            Evidence.user_id == user.id,
            Evidence.goal_id == goal.id,
            Evidence.kind == "risk_forecast",
        )
        .order_by(Evidence.created_at.desc())
        .limit(limit)
    ).all()
    point_map = {
        point.name: point
        for point in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    }
    history = []
    for row in rows:
        if kp_id is not None:
            point = point_map.get(row.subject)
            if point is None or point.id != kp_id:
                continue
        try:
            payload = json.loads(row.payload)
        except Exception:
            payload = {}
        history.append(
            {
                "subject": row.subject,
                "risk_score": payload.get("risk_score"),
                "level": payload.get("level"),
                "confidence": payload.get("confidence"),
                "factors": payload.get("factors", []),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return history


def apply_verification(
    db: Session, user: User, goal: Goal, prediction_id: int, passed: bool
) -> Dict:
    row = db.get(RiskPrediction, prediction_id)
    if row is None or row.user_id != user.id or row.goal_id != goal.id:
        raise ValueError("风险记录不存在")
    point = db.get(KnowledgePoint, row.kp_id)
    if passed:
        row.status = "false_positive"
        message = "验证通过，已排除该风险（记为误报，不再提示）"
        created_task = None
    else:
        row.status = "verified"
        message = "验证未通过，风险确认，已生成修复任务"
        created_task = None
        if point:
            gap = db.scalar(
                select(KnowledgeGap).where(
                    KnowledgeGap.user_id == user.id,
                    KnowledgeGap.goal_id == goal.id,
                    KnowledgeGap.kp_id == point.id,
                )
            )
            if gap is None:
                gap = KnowledgeGap(
                    user_id=user.id,
                    goal_id=goal.id,
                    kp_id=point.id,
                    status="verified",
                    evidence=f"风险验证未通过，风险分 {row.risk_score}",
                    source="risk_forecast",
                    verified_at=datetime.utcnow(),
                )
                db.add(gap)
            else:
                gap.status = "verified"
                gap.verified_at = datetime.utcnow()
            task = Task(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=point.id,
                day=date.today(),
                title=f"漏洞修复：{point.name}",
                type="remedial",
                duration_min=20,
                status="pending",
                reason="知识漏洞预警验证未通过，生成针对性修复任务。",
                priority=3.6,
                source="risk_forecast",
            )
            db.add(task)
            db.flush()
            created_task = task.id
    row.updated_at = datetime.utcnow()
    record_evidence(
        db,
        user.id,
        goal.id,
        "risk_verification",
        point.name if point else str(prediction_id),
        {"passed": passed, "status": row.status, "task_id": created_task},
        message,
        engine="rule",
    )
    db.commit()
    return {"id": row.id, "status": row.status, "message": message, "task_id": created_task}


def submit_feedback(
    db: Session, user: User, goal: Goal, prediction_id: int, verdict: str
) -> Dict:
    if verdict not in ("false_positive", "confirmed"):
        raise ValueError("反馈只能是 false_positive 或 confirmed")
    row = db.get(RiskPrediction, prediction_id)
    if row is None or row.user_id != user.id or row.goal_id != goal.id:
        raise ValueError("风险记录不存在")
    row.status = "false_positive" if verdict == "false_positive" else "verified"
    row.updated_at = datetime.utcnow()
    record_evidence(
        db,
        user.id,
        goal.id,
        "risk_feedback",
        str(row.kp_id),
        {"verdict": verdict},
        "用户反馈风险" + ("误报" if verdict == "false_positive" else "确认"),
        engine="rule",
    )
    db.commit()
    return {"id": row.id, "status": row.status}