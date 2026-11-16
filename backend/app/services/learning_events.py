"""统一学习事件流与可复算的掌握度明细。"""

import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import KnowledgePoint, LearningEvent, Mastery, MasteryHistory
from . import event_bus

EVENT_LABELS = {
    "answer": "答题",
    "review": "闪卡复习",
    "task_done": "完成任务",
    "task_skip": "跳过任务",
    "material": "资料学习",
    "hint": "使用提示",
    "quiz": "随堂测",
    "document_search": "资料检索",
    "recall": "复述检查",
    "resource_generate": "资源生成",
}


def record_event(
    db: Session,
    user_id: int,
    goal_id: int,
    event_type: str,
    kp_id: Optional[int] = None,
    payload: Optional[Dict] = None,
) -> LearningEvent:
    event = LearningEvent(
        user_id=user_id,
        goal_id=goal_id,
        event_type=event_type[:32],
        kp_id=kp_id,
        payload=json.dumps(payload or {}, ensure_ascii=False, default=str)[:6000],
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    db.flush()
    # 文档 7.5：事件交给总教练路由，写入 events 与处理链
    event_bus.publish(db, event_type, user_id, goal_id, payload)
    return event


def event_to_dict(row: LearningEvent) -> Dict:
    try:
        payload = json.loads(row.payload)
    except Exception:
        payload = {}
    return {
        "id": row.id,
        "event_type": row.event_type,
        "label": EVENT_LABELS.get(row.event_type, row.event_type),
        "kp_id": row.kp_id,
        "payload": payload,
        "occurred_at": row.occurred_at,
    }


def list_events(
    db: Session,
    user_id: int,
    goal_id: int,
    limit: int = 50,
    event_type: Optional[str] = None,
) -> List[Dict]:
    query = select(LearningEvent).where(
        LearningEvent.user_id == user_id, LearningEvent.goal_id == goal_id
    )
    if event_type:
        query = query.where(LearningEvent.event_type == event_type)
    rows = db.scalars(query.order_by(LearningEvent.occurred_at.desc()).limit(limit)).all()
    return [event_to_dict(row) for row in rows]


def event_stats(db: Session, user_id: int, goal_id: int) -> Dict:
    rows = db.execute(
        select(LearningEvent.event_type, func.count(LearningEvent.id))
        .where(LearningEvent.user_id == user_id, LearningEvent.goal_id == goal_id)
        .group_by(LearningEvent.event_type)
    ).all()
    by_type = [
        {"event_type": event_type, "label": EVENT_LABELS.get(event_type, event_type), "count": count}
        for event_type, count in rows
    ]
    since = datetime.utcnow() - timedelta(days=7)
    recent = db.scalar(
        select(func.count(LearningEvent.id)).where(
            LearningEvent.user_id == user_id,
            LearningEvent.goal_id == goal_id,
            LearningEvent.occurred_at >= since,
        )
    ) or 0
    return {
        "total": sum(item["count"] for item in by_type),
        "recent_7d": int(recent),
        "by_type": by_type,
    }


def mastery_detail(db: Session, user_id: int, kp_id: int) -> Dict:
    point = db.get(KnowledgePoint, kp_id)
    if point is None:
        raise ValueError("知识点不存在")
    mastery = db.scalar(
        select(Mastery).where(Mastery.user_id == user_id, Mastery.kp_id == kp_id)
    )
    events = db.scalars(
        select(LearningEvent)
        .where(
            LearningEvent.user_id == user_id,
            LearningEvent.kp_id == kp_id,
            LearningEvent.event_type == "answer",
        )
        .order_by(LearningEvent.occurred_at.asc())
    ).all()
    evidence_count = len(events)
    correct = 0
    for row in events:
        try:
            payload = json.loads(row.payload)
        except Exception:
            payload = {}
        if payload.get("correct"):
            correct += 1
    accuracy = round(correct / evidence_count, 3) if evidence_count else 0.0
    confidence = min(0.9, round(0.2 + evidence_count * 0.05, 2))

    current_value = round(mastery.value, 4) if mastery else 0.0
    baseline = current_value
    history = db.scalars(
        select(MasteryHistory)
        .where(MasteryHistory.user_id == user_id, MasteryHistory.kp_id == kp_id)
        .order_by(MasteryHistory.day.asc())
    ).all()
    week_ago = date.today() - timedelta(days=7)
    for row in history:
        if row.day <= week_ago:
            baseline = row.value
    trend = round(current_value - baseline, 4)

    calculations = [
        {"rule": "证据数量", "value": evidence_count, "detail": "该知识点的答题事件数"},
        {"rule": "正确率", "value": accuracy, "detail": "答题事件中正确的比例"},
        {
            "rule": "置信度",
            "value": confidence,
            "detail": "0.2 + 0.05×证据数，上限 0.9；证据少于 3 标记证据不足",
        },
        {"rule": "趋势", "value": trend, "detail": "当前掌握度减去 7 天前快照"},
    ]
    return {
        "kp_id": kp_id,
        "kp_name": point.name,
        "mastery": current_value,
        "review_stage": mastery.review_stage if mastery else 0,
        "next_review_at": mastery.next_review_at if mastery else None,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "accuracy": accuracy,
        "trend": trend,
        "insufficient": evidence_count < 3,
        "calculations": calculations,
        "version": "mastery-rule-v1",
    }