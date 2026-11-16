"""思维路径回放服务单元测试。

覆盖四类错因的规则拆解、LLM 结果校验与回退、回放结果复用、
证据链写入以及序列化容错。全部 LLM 交互均使用假客户端，不发起真实请求。
"""

import asyncio
import json

import pytest
from sqlalchemy import func, select

from app import llm as llm_module
from app.models import Evidence, Mistake, ThoughtTrace
from app.services import thought_trace as thought_trace_module
from app.services.thought_trace import _fallback, get_or_create_trace, trace_to_dict


def _mistake(db, user, goal, category="concept", label="概念不清"):
    item = Mistake(
        user_id=user.id,
        goal_id=goal.id,
        question="请选出正确的时态",
        user_answer="A",
        correct_answer="B",
        category=category,
        category_label=label,
        suggestion="先复习时态定义",
    )
    db.add(item)
    db.flush()
    return item


def _enable_llm(monkeypatch, payload):
    monkeypatch.setattr(llm_module.llm, "base_url", "https://fake.local/v1")
    monkeypatch.setattr(llm_module.llm, "api_key", "test-key")

    async def fake_chat_json(system, user):
        return payload

    monkeypatch.setattr(llm_module.llm, "chat_json", fake_chat_json)
    assert llm_module.llm.available is True


# --------------------------------------------------------------------------
# 规则回退
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category,error_step,step_total,title",
    [
        ("concept", 0, 3, "没有先确认概念定义"),
        ("method", 1, 4, "方法选择错误"),
        ("careless", 2, 3, "跳过了最后 10 秒检查"),
        ("time", 0, 3, "在难题上停留过久"),
        ("unknown", 0, 3, "在难题上停留过久"),
    ],
)
def test_fallback_splits_steps_by_category(category, error_step, step_total, title):
    mistake = Mistake(question="题目", category=category)

    data = _fallback(mistake)

    assert data["error_step"] == error_step
    assert len(data["steps"]) == step_total
    assert data["steps"][error_step]["verdict"] != "正确"
    assert title in data["steps"][error_step]["issue"]
    assert data["summary"].startswith(f"错误发生在第 {error_step + 1} 步：")
    assert data["summary"].endswith(data["steps"][error_step]["issue"] + "。")


def test_fallback_step_indexes_are_sequential():
    data = _fallback(Mistake(question="题目", category="method"))

    assert [step["index"] for step in data["steps"]] == [0, 1, 2, 3]


# --------------------------------------------------------------------------
# 生成与缓存
# --------------------------------------------------------------------------


def test_get_or_create_trace_persists_rule_result_and_evidence(db, db_user_goal):
    user, goal = db_user_goal
    mistake = _mistake(db, user, goal, "method", "方法不会")
    db.commit()

    trace = asyncio.run(get_or_create_trace(db, user, goal, mistake))

    assert trace.id is not None
    assert trace.user_id == user.id
    assert trace.goal_id == goal.id
    assert trace.mistake_id == mistake.id
    assert trace.engine == "rule"
    assert trace.error_step == 1
    steps = json.loads(trace.steps)
    assert len(steps) == 4
    assert steps[1]["verdict"] == "偏离"

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "thought_trace")).one()
    payload = json.loads(evidence.payload)
    assert payload["mistake_id"] == mistake.id
    assert payload["category"] == "method"
    assert payload["error_step"] == 1
    assert len(payload["steps"]) == 4
    assert evidence.output == trace.summary
    assert evidence.engine == "rule"


def test_get_or_create_trace_reuses_existing_record(db, db_user_goal):
    user, goal = db_user_goal
    mistake = _mistake(db, user, goal)
    db.commit()

    first = asyncio.run(get_or_create_trace(db, user, goal, mistake))
    second = asyncio.run(get_or_create_trace(db, user, goal, mistake))

    assert first.id == second.id
    total = db.scalar(select(func.count()).select_from(ThoughtTrace))
    assert total == 1
    evidence_total = db.scalar(select(func.count()).select_from(Evidence))
    assert evidence_total == 1


def test_get_or_create_trace_uses_llm_steps_when_valid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    mistake = _mistake(db, user, goal, "careless", "粗心")
    db.commit()
    _enable_llm(
        monkeypatch,
        {
            "steps": [
                {"index": 9, "thought": "读题", "verdict": "正确", "issue": ""},
                {"index": 9, "thought": "代入公式", "verdict": "偏离", "issue": "漏掉了负号"},
                {"index": 9, "thought": "检查", "verdict": "缺失", "issue": "没有检查"},
            ],
            "error_step": 1,
            "summary": "漏掉负号导致结果相反。",
        },
    )

    trace = asyncio.run(get_or_create_trace(db, user, goal, mistake))

    assert trace.engine == "llm"
    assert trace.error_step == 1
    assert trace.summary == "漏掉负号导致结果相反。"
    steps = json.loads(trace.steps)
    # 索引按顺序重排，忽略 LLM 返回的原始 index
    assert [step["index"] for step in steps] == [0, 1, 2]
    assert steps[1]["issue"] == "漏掉了负号"
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "thought_trace")).one()
    assert evidence.engine == "llm"


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-dict",
        {"steps": "oops"},
        {"steps": []},
        {"steps": [{"thought": "思考"}], "error_step": 5},
        {"steps": [{"thought": "思考"}], "error_step": "1"},
        {"steps": ["not-a-dict"], "error_step": 0},
    ],
)
def test_get_or_create_trace_falls_back_on_invalid_llm_output(
    db, db_user_goal, monkeypatch, payload
):
    user, goal = db_user_goal
    mistake = _mistake(db, user, goal, "careless", "粗心")
    db.commit()
    _enable_llm(monkeypatch, payload)

    trace = asyncio.run(get_or_create_trace(db, user, goal, mistake))

    assert trace.engine == "rule"
    assert trace.error_step == 2
    assert "跳过了最后 10 秒检查" in trace.summary


def test_get_or_create_trace_truncates_long_llm_fields(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    mistake = _mistake(db, user, goal)
    db.commit()
    _enable_llm(
        monkeypatch,
        {
            "steps": [
                {
                    "thought": "思" * 500,
                    "verdict": "正确的判断结果",
                    "issue": "问" * 500,
                }
            ],
            "error_step": 0,
            "summary": "总" * 500,
        },
    )

    trace = asyncio.run(get_or_create_trace(db, user, goal, mistake))

    steps = json.loads(trace.steps)
    assert len(steps[0]["thought"]) == 200
    assert steps[0]["verdict"] == "正确的判断结果"
    assert len(steps[0]["issue"]) == 200
    assert len(trace.summary) == 300


def test_get_or_create_trace_skips_llm_when_unavailable(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    mistake = _mistake(db, user, goal, "time", "时间不够")
    db.commit()
    monkeypatch.setattr(llm_module.llm, "base_url", "")
    monkeypatch.setattr(llm_module.llm, "api_key", "")

    trace = asyncio.run(get_or_create_trace(db, user, goal, mistake))

    assert llm_module.llm.available is False
    assert trace.engine == "rule"
    assert "在难题上停留过久" in trace.summary


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------


def test_trace_to_dict_parses_steps(db_user_goal):
    trace = ThoughtTrace(
        mistake_id=12,
        error_step=1,
        summary="总结",
        steps=json.dumps([{"index": 0, "thought": "思考", "verdict": "正确", "issue": ""}]),
        engine="llm",
    )

    data = trace_to_dict(trace)

    assert data == {
        "mistake_id": 12,
        "error_step": 1,
        "summary": "总结",
        "steps": [{"index": 0, "thought": "思考", "verdict": "正确", "issue": ""}],
        "engine": "llm",
    }


def test_trace_to_dict_tolerates_broken_steps():
    trace = ThoughtTrace(mistake_id=3, steps="not-json", summary="坏数据", engine="rule")

    data = trace_to_dict(trace)

    assert data["steps"] == []
    assert data["summary"] == "坏数据"