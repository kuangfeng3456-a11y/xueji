"""学习证据链：记录每个 AI 判断的输入、规则、输出与来源，支持追溯（2.0）。"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Evidence, User


def record_evidence(
    db: Session,
    user_id: int,
    goal_id: int,
    kind: str,
    subject: str,
    payload: Dict[str, Any],
    output: str,
    engine: str = "rule",
    commit: bool = False,
    prompt_id: Optional[str] = None,
    validation: str = "passed",
    route: str = "",
) -> Evidence:
    enriched: Dict[str, Any] = dict(payload or {})
    enriched.setdefault("evidence_version", "2.0")
    enriched.setdefault(
        "snapshot_id",
        f"ev_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
    )
    if prompt_id:
        enriched.setdefault("prompt_id", prompt_id)
    enriched.setdefault("validation", validation)
    enriched.setdefault("route", route or engine)
    enriched.setdefault("fallback", engine != "llm")

    evidence = Evidence(
        user_id=user_id,
        goal_id=goal_id,
        kind=kind,
        subject=subject[:120],
        payload=json.dumps(enriched, ensure_ascii=False, default=str)[:6000],
        output=(output or "")[:2000],
        engine=engine,
    )
    db.add(evidence)
    db.flush()
    if commit:
        db.commit()
        db.refresh(evidence)
    return evidence


def list_evidence(
    db: Session, user: User, goal_id: int, kind: Optional[str] = None, limit: int = 40
) -> List[Dict[str, Any]]:
    query = select(Evidence).where(Evidence.user_id == user.id, Evidence.goal_id == goal_id)
    if kind:
        query = query.where(Evidence.kind == kind)
    rows = db.scalars(query.order_by(Evidence.created_at.desc()).limit(limit)).all()
    result = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except Exception:
            payload = {}
        result.append(
            {
                "id": row.id,
                "kind": row.kind,
                "subject": row.subject,
                "payload": payload,
                "output": row.output,
                "engine": row.engine,
                "created_at": row.created_at,
            }
        )
    return result