"""模型网关审计与档位路由（文档 7.4 / 6.4）。"""

import asyncio
import json

from sqlalchemy import select

from app.config import settings
from app.llm import llm
from app.models import LlmCall
from app.services.llm_audit import daily_tokens, estimate_tokens, record_llm_call


def run(coro):
    return asyncio.run(coro)


def test_record_llm_call_persists_all_fields(db):
    record_llm_call(
        trace_id="trace-1",
        user_id=None,
        prompt_id="P03",
        prompt_version="2.0.0",
        prompt_hash="a" * 64,
        model="deepseek-chat",
        route="primary",
        tier="fast",
        tokens_in=120,
        tokens_out=40,
        latency_ms=88,
        success=True,
        validator_result="passed",
    )

    row = db.scalars(select(LlmCall)).one()
    assert row.prompt_id == "P03"
    assert row.prompt_version == "2.0.0"
    assert row.tier == "fast"
    assert row.tokens_in == 120
    assert row.tokens_out == 40
    assert row.latency_ms == 88
    assert row.success is True
    assert row.fallback is False
    assert row.validator_result == "passed"


def test_chat_with_prompt_id_records_rule_fallback(db):
    text = run(llm.chat("system", "user", prompt_id="P07", prompt_version="2.0.0"))

    assert text is None  # 测试环境强制禁用真实模型
    row = db.scalars(select(LlmCall)).one()
    assert row.prompt_id == "P07"
    assert row.success is False
    assert row.fallback is True
    assert "未配置" in row.error


def test_chat_without_prompt_id_does_not_write_audit(db):
    run(llm.chat("system", "user"))
    assert db.scalars(select(LlmCall)).all() == []


def test_tier_models_follow_configuration(monkeypatch):
    monkeypatch.setattr(settings, "LLM_TIER_FAST", "fast-model")
    monkeypatch.setattr(settings, "LLM_TIER_GENERAL", "")
    monkeypatch.setattr(settings, "LLM_TIER_REASONING", "reasoning-model")

    assert llm._model_for("fast") == "fast-model"
    assert llm._model_for("reasoning") == "reasoning-model"
    assert llm._model_for("general") == llm.model  # 未配置档位回落主模型
    assert llm._model_for("") == llm.model


def test_stats_expose_tier_models_and_budget(monkeypatch):
    monkeypatch.setattr(settings, "LLM_TIER_FAST", "fast-model")
    stats = llm.stats()
    assert stats["models"]["fast"] == "fast-model"
    assert "general" in stats["models"]
    assert stats["daily_token_budget"] == settings.LLM_DAILY_TOKEN_BUDGET


def test_estimation_helpers():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 2
    assert daily_tokens(None) == 0


def test_daily_tokens_sums_today_for_user(db):
    from datetime import datetime

    db.add_all(
        [
            LlmCall(user_id=42, tokens_in=30, tokens_out=10, created_at=datetime.utcnow()),
            LlmCall(user_id=42, tokens_in=5, tokens_out=5, created_at=datetime.utcnow()),
            LlmCall(user_id=43, tokens_in=999, created_at=datetime.utcnow()),
        ]
    )
    db.commit()

    assert daily_tokens(42) == 50


def test_budget_blocks_calls(monkeypatch):
    monkeypatch.setattr(settings, "LLM_DAILY_TOKEN_BUDGET", 10)
    monkeypatch.setattr(llm, "base_url", "http://127.0.0.1:9/v1")
    monkeypatch.setattr(llm, "api_key", "test-key")
    monkeypatch.setattr(llm, "_budget_exceeded", lambda user_id: True)

    text = run(llm.chat("s", "u", user_id=1, prompt_id="P12"))
    assert text is None
    assert llm.last_error == "daily token budget exceeded"


def test_audit_write_failure_never_breaks_business(monkeypatch):
    from app.services import llm_audit

    def boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(llm_audit, "record_llm_call", boom)
    # 不应抛出异常
    llm._audit(prompt_id="P12", model="m", success=True)


def test_prompt_hash_is_recorded_in_audit(db):
    from app.prompts import library

    digest = library.prompt_hash("P12")
    record_llm_call(prompt_id="P12", prompt_hash=digest, model="m", success=True)
    row = db.scalars(select(LlmCall)).one()
    assert row.prompt_hash == digest
    assert json.dumps(row.prompt_hash)  # 可序列化
