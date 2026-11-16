"""进程内事件总线（文档 7.5）：把「发生了什么」转成「该调用谁」。

设计边界：
- 只做**同步路由决策**：写入 events 表、记录处理器链与是否需要用户确认；
- 真正的业务动作仍由既有 service 执行（判分、重排、降载），总线不重复实现；
- 决策函数是纯函数，便于测试与在证据链中复算。
"""

import json
import uuid
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models import EventLog

# 事件 → (处理链, 是否自动, 是否需要用户确认, 说明)
ROUTES: Dict[str, Tuple[List[str], bool, bool, str]] = {
    "quiz_answered": (
        ["mastery_service", "flashcards", "diagnoser", "planner"],
        True,
        False,
        "判分 → 更新掌握度与复习日 → 错因归因 → 必要时重排",
    ),
    "task_overdue": (
        ["planner", "coach"],
        True,
        False,
        "顺延并计算扰动度；连续逾期则降档，教练说明原因",
    ),
    "fatigue_high": (
        ["planner", "coach", "rest_station"],
        True,
        False,
        "降载到 1 个核心任务并推荐恢复站",
    ),
    "phase_changed": (
        ["planner", "decision_explainer"],
        False,
        True,
        "按新阶段重新配比，解释变化并提示确认",
    ),
    "risk_detected": (
        ["risk_rescue", "panel"],
        False,
        True,
        "规则先算调整前后，风险官解释，评审团复核，等待确认",
    ),
    "material_uploaded": (
        ["material_parser", "freshness_radar"],
        True,
        False,
        "清洗与注入探测 → 知识点抽取 → 时效雷达",
    ),
    "safety_event": (
        ["wellbeing_guard"],
        True,
        False,
        "只做关怀与转介，不进入学习建议",
    ),
}

EXTRA_HANDLERS: Dict[str, Callable[[Dict], Dict]] = {}

# 现有业务事件名 → 文档 7.5 的事件名，便于路由与审计对齐
ALIASES = {
    "answer": "quiz_answered",
    "quiz": "quiz_answered",
    "review": "quiz_answered",
    "recall": "quiz_answered",
    "material": "material_uploaded",
    "task_skip": "task_overdue",
    "task_done": "task_completed",
    "hint": "coach_note",
    "document_search": "coach_note",
    "resource_generate": "coach_note",
}


def register(event_type: str):
    """注册额外处理器（返回附加决策），用于扩展而不改路由表。"""

    def decorator(func: Callable[[Dict], Dict]):
        EXTRA_HANDLERS[event_type] = func
        return func

    return decorator


def route(event_type: str, payload: Optional[Dict] = None) -> Dict:
    """总教练路由决策：调用哪些处理者、是否自动、是否需要确认。"""
    route_type = ALIASES.get(event_type, event_type)
    handlers, auto, needs_confirm, note = ROUTES.get(
        route_type,
        (["coach"], True, False, "未知事件：交给教练按通用语气说明"),
    )
    decision = {
        "type": event_type,
        "route_type": route_type,
        "handlers": list(handlers),
        "auto": auto,
        "needs_confirmation": needs_confirm,
        "note": note,
    }
    extra = EXTRA_HANDLERS.get(event_type)
    if extra:
        try:
            decision.update(extra(payload or {}) or {})
        except Exception:  # noqa: BLE001 - 扩展处理器失败不影响主链路
            decision["handler_error"] = True
    return decision


def publish(
    db: Session,
    event_type: str,
    user_id: Optional[int],
    goal_id: Optional[int],
    payload: Optional[Dict] = None,
) -> Dict:
    """写入事件并返回路由决策；event_id 便于幂等重放。"""
    decision = route(event_type, payload)
    event_id = uuid.uuid4().hex
    db.add(
        EventLog(
            event_id=event_id,
            type=event_type[:32],
            user_id=user_id,
            goal_id=goal_id,
            payload=json.dumps(payload or {}, ensure_ascii=False, default=str)[:4000],
            handled_by=",".join(decision["handlers"])[:64],
        )
    )
    db.flush()
    return {"event_id": event_id, **decision}


def recent_events(db: Session, user_id: Optional[int] = None, limit: int = 20) -> List[Dict]:
    from sqlalchemy import select

    query = select(EventLog).order_by(EventLog.id.desc()).limit(max(1, min(limit, 100)))
    if user_id:
        query = query.where(EventLog.user_id == user_id)
    rows = db.scalars(query).all()
    return [
        {
            "event_id": row.event_id,
            "type": row.type,
            "handled_by": row.handled_by.split(",") if row.handled_by else [],
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "payload_preview": (row.payload or "")[:200],
        }
        for row in rows
    ]
