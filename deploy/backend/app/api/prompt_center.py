"""提示词中心与模型调用审计接口（文档 6.6 / 7.1 可信度中心）。

- GET  /prompts             提示词清单（17 条任务提示词 + 前缀，含版本哈希）
- GET  /prompts/versions    注册表内容
- GET  /prompts/{pid}       单条提示词正文与校验规则
- POST /prompts/sync        运维：把提示词库同步进 prompt_versions
- GET  /llm-calls           近 1 小时/24 小时调用统计与最近调用明细
"""

from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import LlmCall, User
from ..prompts import library
from ..prompts.registry import list_versions, sync_prompt_versions
from ..services.eval_cases import list_cases
from ..services.safety_events import list_safety_events

router = APIRouter(tags=["提示词中心"])


@router.get("/prompts")
def prompts(user: User = Depends(get_current_user)) -> Dict:
    items = library.list_prompts()
    return {
        "version": library.PROMPT_VERSION,
        "total": len(items),
        "envelope_fields": list(library.ENVELOPE_FIELDS),
        "items": items,
    }


@router.get("/prompts/versions")
def prompt_versions(
    prompt_id: str = Query(default="", description="按提示词编号过滤，如 P03"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict:
    rows = list_versions(db, prompt_id)
    return {"total": len(rows), "items": rows}


@router.post("/prompts/sync")
def prompt_sync(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict:
    return sync_prompt_versions(db)


@router.get("/prompts/{prompt_id}")
def prompt_detail(
    prompt_id: str,
    user: User = Depends(get_current_user),
) -> Dict:
    try:
        item = library.get(prompt_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="提示词不存在")
    return {
        **item,
        "hash": library.prompt_hash(prompt_id),
        "placeholders": library.placeholders(prompt_id),
    }


@router.get("/prompts/{prompt_id}/cases")
def prompt_cases(
    prompt_id: str,
    tag: str = Query(default="", description="normal / boundary / adversarial"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict:
    try:
        library.get(prompt_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="提示词不存在")
    rows = list_cases(db, prompt_id=prompt_id, tag=tag)
    return {"total": len(rows), "items": rows}


@router.get("/safety-events")
def safety_events(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict:
    rows = list_safety_events(db, limit=limit)
    return {"total": len(rows), "items": rows}


def _aggregate(db: Session, since: datetime) -> Dict:
    total = db.scalar(
        select(func.count(LlmCall.id)).where(LlmCall.created_at >= since)
    ) or 0
    success = db.scalar(
        select(func.count(LlmCall.id)).where(
            LlmCall.created_at >= since, LlmCall.success.is_(True)
        )
    ) or 0
    fallback = db.scalar(
        select(func.count(LlmCall.id)).where(
            LlmCall.created_at >= since, LlmCall.fallback.is_(True)
        )
    ) or 0
    cache_hit = db.scalar(
        select(func.count(LlmCall.id)).where(
            LlmCall.created_at >= since, LlmCall.cache_hit.is_(True)
        )
    ) or 0
    avg_latency = db.scalar(
        select(func.avg(LlmCall.latency_ms)).where(LlmCall.created_at >= since)
    ) or 0
    return {
        "calls": int(total),
        "success": int(success),
        "fallback": int(fallback),
        "cache_hit": int(cache_hit),
        "success_rate": round(success / total, 3) if total else 0.0,
        "fallback_rate": round(fallback / total, 3) if total else 0.0,
        "avg_latency_ms": round(float(avg_latency), 1),
    }


@router.get("/llm-calls")
def llm_calls(
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict:
    now = datetime.utcnow()
    rows = db.scalars(
        select(LlmCall).where(LlmCall.user_id == user.id).order_by(LlmCall.id.desc()).limit(limit)
    ).all()
    by_prompt: List[Dict] = []
    counts = db.execute(
        select(LlmCall.prompt_id, func.count(LlmCall.id))
        .where(LlmCall.user_id == user.id, LlmCall.created_at >= now - timedelta(days=1))
        .group_by(LlmCall.prompt_id)
    ).all()
    for prompt_id, count in counts:
        by_prompt.append({"prompt_id": prompt_id or "(未标注)", "calls": int(count)})
    recent = [
        {
            "id": row.id,
            "trace_id": row.trace_id,
            "prompt_id": row.prompt_id,
            "prompt_version": row.prompt_version,
            "model": row.model,
            "route": row.route,
            "tier": row.tier,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "latency_ms": row.latency_ms,
            "cache_hit": row.cache_hit,
            "success": row.success,
            "fallback": row.fallback,
            "validator_result": row.validator_result,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return {
        "hour": _aggregate(db, now - timedelta(hours=1)),
        "day": _aggregate(db, now - timedelta(days=1)),
        "by_prompt": by_prompt,
        "recent": recent,
        "recent_total": len(recent),
    }
