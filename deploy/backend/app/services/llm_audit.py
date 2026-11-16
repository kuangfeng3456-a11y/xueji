"""模型调用审计（文档 7.4 llm_calls）。

审计写入失败绝不能影响业务：所有异常只记录告警。
"""

import logging
from typing import Optional

logger = logging.getLogger("xueji.llm")


def estimate_tokens(text: Optional[str]) -> int:
    """粗略 token 估算（中文约 1 字 ≈ 1 token，英文 4 字符 ≈ 1 token）。"""
    if not text:
        return 0
    return max(1, len(text) // 2)


def record_llm_call(
    *,
    trace_id: str = "",
    user_id: Optional[int] = None,
    prompt_id: str = "",
    prompt_version: str = "",
    prompt_hash: str = "",
    model: str = "",
    route: str = "primary",
    tier: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    cache_hit: bool = False,
    success: bool = False,
    repaired: bool = False,
    fallback: bool = False,
    validator_result: str = "",
    error: str = "",
) -> None:
    """写入一条调用审计；数据库不可用时静默降级为日志。"""
    try:
        from ..database import SessionLocal
        from ..models import LlmCall

        with SessionLocal() as db:
            db.add(
                LlmCall(
                    trace_id=trace_id[:64],
                    user_id=user_id,
                    prompt_id=prompt_id[:16],
                    prompt_version=prompt_version[:16],
                    prompt_hash=prompt_hash[:64],
                    model=model[:64],
                    route=route[:16],
                    tier=tier[:16],
                    tokens_in=int(tokens_in),
                    tokens_out=int(tokens_out),
                    latency_ms=int(latency_ms),
                    cache_hit=bool(cache_hit),
                    success=bool(success),
                    repaired=bool(repaired),
                    fallback=bool(fallback),
                    validator_result=validator_result[:32],
                    error=(error or "")[:255],
                )
            )
            db.commit()
    except Exception:  # noqa: BLE001 - 审计失败不影响主流程
        logger.warning("llm_calls 写入失败，已忽略（不影响业务）", exc_info=False)


def daily_tokens(user_id: Optional[int]) -> int:
    """某用户今日已消耗 token（用于日预算判断）。"""
    if not user_id:
        return 0
    try:
        from datetime import date, datetime, time

        from sqlalchemy import func, select

        from ..database import SessionLocal
        from ..models import LlmCall

        start = datetime.combine(date.today(), time.min)
        with SessionLocal() as db:
            total = db.scalar(
                select(func.coalesce(func.sum(LlmCall.tokens_in + LlmCall.tokens_out), 0)).where(
                    LlmCall.user_id == user_id, LlmCall.created_at >= start
                )
            )
        return int(total or 0)
    except Exception:  # noqa: BLE001 - 预算查询失败按未超限处理
        return 0
