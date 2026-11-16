"""ai_content 模块单元测试。

所有用例均通过 Mock 替换 llm / cache，测试期间不会发出任何真实 DeepSeek 请求。
"""

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.ai_content import (
    _rule_insight,
    ai_flashcard_explanation,
    ai_forecast_strategy,
    ai_insight_report,
)

USER = SimpleNamespace(id=7)
GOAL = SimpleNamespace(id=11, exam_name="CET-4", exam_date=date(2026, 12, 31))
TODAY = date(2026, 12, 1)

INSIGHTS = {
    "radar": [
        {"label": "听力", "value": 0.856},
        {"label": "阅读", "value": 0.5},
    ],
    "fatigue": {
        "score": 72,
        "level": "高",
        "factors": ["睡眠不足", "任务堆积"],
        "advice": "建议休息",
    },
    "active_days": 30,
    "total_minutes": 3000,
    "radar_score": 88,
    "achievements": [
        {"name": "坚持之星", "unlocked": True},
        {"name": "未解锁徽章", "unlocked": False},
    ],
}

FORECAST = {
    "recommendation": "保持当前节奏",
    "current_mastery": 0.42,
    "projected_mastery": 0.68,
    "target_mastery": 0.8,
    "required_daily_minutes": 65,
    "days_left": 21,
    "scenarios": [
        {"label": "维持", "daily_minutes": 45, "projected_mastery": 0.68},
        {"label": "加量", "daily_minutes": 90, "projected_mastery": 0.85},
    ],
}

POINT = SimpleNamespace(id=5, name="听力短对话", weight=1.5)


def run(coro):
    """在同步测试中执行协程，避免依赖 pytest-asyncio。"""
    return asyncio.run(coro)


# ---------------------------------------------------------------- 规则文案


def test_rule_insight_renders_all_metrics():
    text = _rule_insight(INSIGHTS)

    assert "近 12 周有 30 天学习记录" in text
    assert "累计 50 小时" in text
    assert "能力结构：听力86%、阅读50%。" in text
    assert "当前疲劳指数 72，建议休息" in text


def test_rule_insight_defaults_for_empty_payload():
    text = _rule_insight({})

    assert "近 12 周有 0 天学习记录" in text
    assert "累计 0 小时" in text
    assert "能力结构：。" in text
    assert "当前疲劳指数 0，" in text


# ---------------------------------------------------------------- 学情诊断


def test_ai_insight_report_returns_rule_fallback_when_llm_unavailable():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = False
        result = run(ai_insight_report(None, USER, GOAL, INSIGHTS, today=TODAY))

    assert result["engine"] == "rule"
    assert result["text"] == _rule_insight(INSIGHTS)
    llm_mock.chat.assert_not_called()
    cache_mock.get_json.assert_not_called()
    cache_mock.set_json.assert_not_called()


def test_ai_insight_report_returns_cached_payload_without_calling_llm():
    cached = {"text": "缓存中的诊断", "engine": "llm"}
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = cached
        result = run(ai_insight_report(None, USER, GOAL, INSIGHTS, today=TODAY))

    assert result is cached
    expected_key = f"ai:insights:{USER.id}:{GOAL.id}:{TODAY.isoformat()}:88:72"
    cache_mock.get_json.assert_called_once_with(expected_key)
    cache_mock.set_json.assert_not_called()
    llm_mock.chat.assert_not_called()


def test_ai_insight_report_builds_prompt_and_caches_llm_text():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat = AsyncMock(return_value="  " + "诊" * 700 + "  ")

        result = run(ai_insight_report(None, USER, GOAL, INSIGHTS, today=TODAY))

    assert result["engine"] == "llm"
    assert result["text"] == "诊" * 600

    system, prompt = llm_mock.chat.await_args.args
    assert "学情诊断教练" in system
    assert "只输出中文正文" in system
    assert "考试：CET-4" in prompt
    assert "剩余 30 天" in prompt
    assert "活跃天数 30" in prompt
    assert "累计 50 小时" in prompt
    assert "能力雷达：听力 86%；阅读 50%" in prompt
    assert "综合指数 88" in prompt
    assert "疲劳指数 72（高）：睡眠不足；任务堆积" in prompt
    assert "已解锁徽章：坚持之星" in prompt
    assert "未解锁徽章" not in prompt
    assert llm_mock.chat.await_args.kwargs == {"temperature": 0.4, "max_tokens": 360}

    expected_key = f"ai:insights:{USER.id}:{GOAL.id}:{TODAY.isoformat()}:88:72"
    cache_mock.set_json.assert_called_once_with(
        expected_key, {"text": "诊" * 600, "engine": "llm"}, ttl=1800
    )


def test_ai_insight_report_falls_back_when_llm_returns_empty():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat = AsyncMock(return_value="")

        result = run(ai_insight_report(None, USER, GOAL, INSIGHTS, today=TODAY))

    assert result == {"text": _rule_insight(INSIGHTS), "engine": "rule"}
    cache_mock.set_json.assert_not_called()


def test_ai_insight_report_defaults_today_and_handles_past_exam():
    goal = SimpleNamespace(
        id=3, exam_name="期末考试", exam_date=date.today() - timedelta(days=5)
    )
    insights = {
        "radar": [],
        "fatigue": {},
        "active_days": 1,
        "total_minutes": 0,
        "radar_score": 10,
        "achievements": [{"name": "未解锁徽章", "unlocked": False}],
    }
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat = AsyncMock(return_value="ok")
        result = run(ai_insight_report(None, USER, goal, insights))

    assert result == {"text": "ok", "engine": "llm"}
    prompt = llm_mock.chat.await_args.args[1]
    assert "考试：期末考试" in prompt
    assert "剩余 0 天" in prompt
    assert "能力雷达：；综合指数 10" in prompt
    assert "已解锁徽章：暂无" in prompt


# ---------------------------------------------------------------- 冲刺策略


def test_ai_forecast_strategy_rule_fallback_when_unavailable():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = False
        result = run(ai_forecast_strategy(FORECAST, GOAL))

    assert result == {"text": "保持当前节奏", "engine": "rule"}
    llm_mock.chat.assert_not_called()
    cache_mock.get_json.assert_not_called()


def test_ai_forecast_strategy_returns_cached_payload():
    cached = {"text": "缓存策略", "engine": "llm"}
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = cached
        result = run(ai_forecast_strategy(FORECAST, GOAL))

    assert result is cached
    expected_key = f"ai:forecast:{GOAL.id}:0.42:0.68:65:21"
    cache_mock.get_json.assert_called_once_with(expected_key)
    cache_mock.set_json.assert_not_called()
    llm_mock.chat.assert_not_called()


def test_ai_forecast_strategy_caches_llm_text():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat = AsyncMock(return_value="  " + "策" * 600 + "  ")

        result = run(ai_forecast_strategy(FORECAST, GOAL))

    assert result == {"text": "策" * 500, "engine": "llm"}

    system, prompt = llm_mock.chat.await_args.args
    assert "考前冲刺策略教练" in system
    assert "只输出中文正文" in system
    assert "考试：CET-4" in prompt
    assert "剩余 21 天" in prompt
    assert "当前掌握度 42%" in prompt
    assert "按当前节奏预计 68%" in prompt
    assert "目标 80%" in prompt
    assert "达标所需每日时长 65 分钟" in prompt
    assert "情景：维持每天45分钟→68%；加量每天90分钟→85%" in prompt
    assert llm_mock.chat.await_args.kwargs == {"temperature": 0.4, "max_tokens": 320}

    expected_key = f"ai:forecast:{GOAL.id}:0.42:0.68:65:21"
    cache_mock.set_json.assert_called_once_with(
        expected_key, {"text": "策" * 500, "engine": "llm"}, ttl=1800
    )


def test_ai_forecast_strategy_falls_back_when_llm_returns_blank():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat = AsyncMock(return_value=None)

        result = run(ai_forecast_strategy(FORECAST, GOAL))

    assert result == {"text": "保持当前节奏", "engine": "rule"}
    cache_mock.set_json.assert_not_called()


# ---------------------------------------------------------------- 闪卡释义


def test_ai_flashcard_explanation_rule_fallback_without_parent():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = False
        result = run(ai_flashcard_explanation(POINT, None, 0.6))

    assert result["engine"] == "rule"
    assert result["explanation"] == "「听力短对话」属于「核心模块」，当前掌握度 60%。"
    assert result["memory_tip"].startswith("先用自己的话复述定义")
    assert result["misconception"].startswith("概念类知识点最常见的错误")
    llm_mock.chat_json.assert_not_called()
    cache_mock.get_json.assert_not_called()


def test_ai_flashcard_explanation_returns_cached_payload():
    cached = {
        "explanation": "缓存的解释",
        "memory_tip": "缓存的技巧",
        "misconception": "缓存的误区",
        "engine": "llm",
        "external": {"available": False, "sources": []},
    }
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = cached
        result = run(ai_flashcard_explanation(POINT, "阅读", 0.6))

    assert result is cached
    cache_mock.get_json.assert_called_once_with(f"ai:card:{POINT.id}")
    llm_mock.chat_json.assert_not_called()
    cache_mock.set_json.assert_not_called()


def test_ai_flashcard_explanation_uses_llm_payload_and_fills_missing_fields():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat_json = AsyncMock(
            return_value={"explanation": "  " + "解" * 250 + "  ", "memory_tip": "", "misconception": ""}
        )

        result = run(ai_flashcard_explanation(POINT, "阅读", 0.6))

    assert result["engine"] == "llm"
    assert result["explanation"] == "解" * 200
    assert result["memory_tip"].startswith("先用自己的话复述定义")
    assert result["misconception"].startswith("概念类知识点最常见的错误")

    system, prompt = llm_mock.chat_json.await_args.args
    assert '"memory_tip"' in system
    assert "只输出 JSON" in system
    assert "知识点：听力短对话" in prompt
    assert "所属模块：阅读" in prompt
    assert "权重：1.5" in prompt
    assert "当前掌握度：60%" in prompt
    cache_mock.set_json.assert_called_once_with(
        f"ai:card:{POINT.id}", result, ttl=86400
    )


def test_ai_flashcard_explanation_keeps_complete_llm_payload():
    payload = {
        "explanation": "一句话解释",
        "memory_tip": "一条记忆技巧",
        "misconception": "一个常见误区",
    }
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat_json = AsyncMock(return_value=payload)

        result = run(ai_flashcard_explanation(POINT, None, 0.6))

    assert result["engine"] == "llm"
    for key, value in payload.items():
        assert result[key] == value
    assert "external" in result


def test_ai_flashcard_explanation_falls_back_for_non_dict_response():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat_json = AsyncMock(return_value=["not", "a", "dict"])

        result = run(ai_flashcard_explanation(POINT, "阅读", 0.6))

    assert result["engine"] == "rule"
    assert result["explanation"] == "「听力短对话」属于「阅读」，当前掌握度 60%。"
    cache_mock.set_json.assert_not_called()


def test_ai_flashcard_explanation_falls_back_when_explanation_blank():
    with patch("app.services.ai_content.llm") as llm_mock, patch(
        "app.services.ai_content.cache"
    ) as cache_mock:
        llm_mock.available = True
        cache_mock.get_json.return_value = None
        llm_mock.chat_json = AsyncMock(
            return_value={"explanation": "   ", "memory_tip": "技巧", "misconception": "误区"}
        )

        result = run(ai_flashcard_explanation(POINT, "阅读", 0.6))

    assert result["engine"] == "rule"
    assert "「听力短对话」属于「阅读」" in result["explanation"]
    cache_mock.set_json.assert_not_called()