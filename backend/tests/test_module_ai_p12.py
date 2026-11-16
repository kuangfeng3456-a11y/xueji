"""ModuleAI 走决策解释官 P12（文档 7.1）：统一信封、证据与兜底文案。"""

import asyncio
import json

from app.models import KnowledgePoint
from app.services import module_ai

ENVELOPE = {
    "data": {
        "insights": [
            {
                "finding": "今日计划 30 分钟，准备度 66",
                "so_what": "还有提升空间，先把最高优先级任务做完",
                "evidence": "module_data.剩余天数",
            }
        ],
        "next_actions": ["先完成今日最高优先级任务", "打开学习计划确认本周安排"],
        "caveats": ["近 28 天只有 3 次作答，结论偏保守"],
    },
    "evidence_refs": [],
    "confidence": 0.7,
    "warnings": [],
}


class FakeLLM:
    available = True

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def chat(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        return self.reply


def _seed(db, user, goal):
    db.add(KnowledgePoint(goal_id=goal.id, name="听力", weight=1.0))
    db.commit()


def test_module_ai_uses_p12_envelope(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _seed(db, user, goal)
    fake = FakeLLM(json.dumps(ENVELOPE, ensure_ascii=False))
    monkeypatch.setattr(module_ai, "llm", fake)

    result = asyncio.run(module_ai.generate("cockpit", db, user, goal))

    assert result["engine"] == "llm"
    assert result["prompt"]["id"] == "P12"
    assert result["prompt"]["version"] == "2.0.0"
    assert result["insights"][0].startswith("今日计划 30 分钟")
    assert result["actions"] == ENVELOPE["data"]["next_actions"]
    assert result["caveats"] == ENVELOPE["data"]["caveats"]

    call = fake.calls[0]
    assert call["prompt_id"] == "P12"
    assert call["prompt_version"] == "2.0.0"
    assert call["tier"] == "general"
    assert call["temperature"] == 0.4
    assert call["user_id"] == user.id
    # system 消息由 P00 前缀 + P12 正文 + 输出契约组成
    assert "学迹" in call["system"]
    assert "决策解释官" in call["system"]
    assert "<output_contract>" in call["system"]
    assert "<module>" in call["user"]


def test_module_ai_keeps_rule_fallback_when_envelope_invalid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _seed(db, user, goal)
    monkeypatch.setattr(module_ai, "llm", FakeLLM('{"headline": "缺少信封"}'))

    result = asyncio.run(module_ai.generate("cockpit", db, user, goal))

    assert result["engine"] == "rule"
    assert result["headline"]
    assert "prompt" not in result


def test_module_ai_reports_insufficient_data(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _seed(db, user, goal)
    empty = {
        "data": {"insights": [], "next_actions": [], "caveats": ["需要先积累作答数据"]},
        "evidence_refs": [],
        "confidence": 0.2,
        "warnings": ["low_sample"],
    }
    monkeypatch.setattr(module_ai, "llm", FakeLLM(json.dumps(empty, ensure_ascii=False)))

    result = asyncio.run(module_ai.generate("cockpit", db, user, goal))

    assert result["engine"] == "rule"
    assert "数据不足" in result["ai_note"]


def test_module_api_endpoint_records_prompt_metadata(api, auth, goal, monkeypatch):
    fake = FakeLLM(json.dumps(ENVELOPE, ensure_ascii=False))
    monkeypatch.setattr(module_ai, "llm", fake)

    response = api(
        "POST",
        "/api/module-ai/cockpit",
        token=auth["token"],
        json={"goal_id": goal["id"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prompt"]["id"] == "P12"
    assert body["engine"] == "llm"
