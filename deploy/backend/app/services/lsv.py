"""学习者状态向量 LSV（B1）：统一快照、脱敏与 snapshot_id 证据链。"""

import hashlib
import json
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, LsvSnapshot, Mastery, Mistake, Task, User
from .evidence import record_evidence
from .readiness import build_risks, compute_readiness
from .twin import build_forecast

LSV_VERSION = "2.0"


def _hash_user(user_id: int) -> str:
    return "u_" + hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def build_lsv(db: Session, user: User, goal: Goal, today: Optional[date] = None) -> Dict:
    today = today or date.today()
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    point_map = {point.id: point for point in points}
    masteries = {
        row.kp_id: row
        for row in db.scalars(
            select(Mastery).where(
                Mastery.user_id == user.id, Mastery.kp_id.in_(list(point_map) or [0])
            )
        ).all()
    }
    counts = dict(
        db.execute(
            select(Mistake.kp_id, func.count(Mistake.id))
            .where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
            .group_by(Mistake.kp_id)
        ).all()
    )
    readiness = compute_readiness(db, user, goal, today)
    risks = build_risks(db, user, goal, today)
    forecast = build_forecast(db, user, goal, today)

    knowledge: List[Dict] = []
    for point in points:
        record = masteries.get(point.id)
        value = record.value if record else 0.0
        knowledge.append(
            {
                "kp_id": point.id,
                "name": point.name,
                "weight": round(point.weight, 3),
                "mastery": round(value, 3),
                "review_stage": record.review_stage if record else 0,
                "next_review_at": record.next_review_at.isoformat()
                if record and record.next_review_at
                else None,
                "mistake_count": int(counts.get(point.id, 0) or 0),
                "prereqs": [],
            }
        )

    tasks_today = db.scalars(
        select(Task).where(
            Task.user_id == user.id, Task.goal_id == goal.id, Task.day == today
        )
    ).all()
    overdue = db.scalar(
        select(func.count(Task.id)).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.status == "pending",
            Task.day < today,
        )
    ) or 0

    snapshot_id = f"lsv_{today.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    data = {
        "lsv_version": LSV_VERSION,
        "snapshot_id": snapshot_id,
        "as_of": datetime.utcnow().isoformat(),
        "user_hash": _hash_user(user.id),
        "goal": {
            "name": goal.exam_name,
            "exam_date": goal.exam_date.isoformat(),
            "days_left": max(0, (goal.exam_date - today).days),
            "daily_minutes": goal.daily_minutes,
        },
        "knowledge": knowledge,
        "load": {
            "today_tasks": len(tasks_today),
            "today_planned_min": sum(task.duration_min for task in tasks_today),
            "overdue_tasks": int(overdue),
        },
        "readiness": {
            "score": readiness.get("score"),
            "coverage": readiness.get("coverage"),
            "load_ratio": readiness.get("load_ratio"),
        },
        "risks": [
            {"type": item.get("code"), "level": item.get("level"), "title": item.get("title")}
            for item in risks
        ],
        "forecast": {
            "current_mastery": forecast.get("current_mastery"),
            "horizons": forecast.get("horizons"),
            "uncertainty": forecast.get("uncertainty"),
        },
        "privacy": {
            "note": "LSV 不含姓名、学号、邮箱与心理评估数据；user_id 使用不可逆哈希。",
            "psychology_excluded": True,
        },
    }

    record_evidence(
        db,
        user.id,
        goal.id,
        "lsv_snapshot",
        snapshot_id,
        {"snapshot_id": snapshot_id, "lsv_version": LSV_VERSION, "as_of": data["as_of"]},
        f"LSV 快照 {snapshot_id}",
        engine="rule",
        prompt_id="P00-lsv",
        validation="passed",
        route="rule",
    )
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    db.add(
        LsvSnapshot(
            snapshot_id=snapshot_id,
            user_id=user.id,
            goal_id=goal.id,
            as_of=datetime.utcnow(),
            lsv_version=LSV_VERSION,
            payload=payload,
            hash=digest,
        )
    )
    db.commit()
    data["knowledge_count"] = len(knowledge)
    data["snapshot_hash"] = digest
    return data