"""AI 主动探针与挑战服务单元测试。

覆盖知识点挑选规则、规则出题、LLM 出题结果校验、作答判分、
反脆弱挑战不惩罚掌握度、以及学习证据链写入。

测试全程不发起真实 DeepSeek 请求：LLM 分支统一通过 monkeypatch 注入
假的 ``chat_json``，并额外断言 ``available`` 由测试控制。
"""

import asyncio
import json
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app import llm as llm_module
from app.models import Evidence, Goal, KnowledgePoint, Mastery, Mistake, ProbeItem, User
from app.security import hash_password
from app.services import probes as probes_module
from app.services.probes import (
    KIND_BRIEF,
    VALID_KINDS,
    generate_probes,
    probe_to_dict,
    submit_probe,
)


# --------------------------------------------------------------------------
# 测试数据辅助
# --------------------------------------------------------------------------


def _point(db, goal, name, weight=1.0, parent_id=None):
    point = KnowledgePoint(goal_id=goal.id, name=name, weight=weight, parent_id=parent_id)
    db.add(point)
    db.flush()
    return point


def _mastery(db, user, point, value):
    record = Mastery(user_id=user.id, kp_id=point.id, value=value)
    db.add(record)
    db.flush()
    return record


def _mistake(db, user, goal, point):
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            question="错题",
            category="concept",
            category_label="概念不清",
        )
    )
    db.flush()


def _enable_llm(monkeypatch, payload):
    monkeypatch.setattr(llm_module.llm, "base_url", "https://fake.local/v1")
    monkeypatch.setattr(llm_module.llm, "api_key", "test-key")

    async def fake_chat_json(system, user):
        return payload

    monkeypatch.setattr(llm_module.llm, "chat_json", fake_chat_json)
    assert llm_module.llm.available is True


def _probe(db, user, goal, point, answer_index=0, kind="probe", status="pending"):
    item = ProbeItem(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=point.id if point else None,
        kind=kind,
        question="探针题目",
        options=json.dumps(["A", "B", "C", "D"], ensure_ascii=False),
        answer_index=answer_index,
        explanation="解析",
        status=status,
    )
    db.add(item)
    db.flush()
    return item


# --------------------------------------------------------------------------
# 知识点挑选
# --------------------------------------------------------------------------


def test_leaves_only_returns_child_points(db, db_user_goal):
    user, goal = db_user_goal
    parent = _point(db, goal, "阅读", 2.0)
    child = _point(db, goal, "仔细阅读", 1.5, parent_id=parent.id)

    leaves = probes_module._leaves(db, goal.id)

    assert [point.name for point in leaves] == ["仔细阅读"]
    assert leaves[0].id == child.id


def test_leaves_falls_back_to_all_points_when_no_leaf(db, db_user_goal):
    user, goal = db_user_goal
    # 所有知识点都带有 parent_id，但父节点本身不在库中，叶子集合为空
    first = _point(db, goal, "孤立知识点一", 1.0, parent_id=999)
    second = _point(db, goal, "孤立知识点二", 1.0, parent_id=999)

    leaves = probes_module._leaves(db, goal.id)

    assert {point.id for point in leaves} == {first.id, second.id}


def test_pick_points_probe_prefers_low_mastery_and_more_mistakes(db, db_user_goal):
    user, goal = db_user_goal
    weak = _point(db, goal, "薄弱点", 1.0)
    confused = _point(db, goal, "易错点", 1.0)
    strong = _point(db, goal, "已掌握", 1.0)
    _mastery(db, user, weak, 0.1)
    _mastery(db, user, confused, 0.1)
    _mastery(db, user, strong, 0.9)
    _mistake(db, user, goal, confused)

    picked = probes_module._pick_points(db, user, goal, "probe", None, 1)

    # 掌握度相同（0.1）时，错题更多的“易错点”排在前面
    assert [point.name for point in picked] == ["易错点"]


def test_pick_points_transfer_uses_middle_mastery_band(db, db_user_goal):
    user, goal = db_user_goal
    low = _point(db, goal, "低掌握", 1.0)
    middle = _point(db, goal, "中等掌握", 1.0)
    high = _point(db, goal, "高掌握", 1.0)
    _mastery(db, user, low, 0.1)
    _mastery(db, user, middle, 0.5)
    _mastery(db, user, high, 0.95)

    picked = probes_module._pick_points(db, user, goal, "transfer", None, 2)

    assert [point.name for point in picked] == ["中等掌握"]


def test_pick_points_transfer_falls_back_to_all_when_band_empty(db, db_user_goal):
    user, goal = db_user_goal
    low = _point(db, goal, "低掌握", 1.0)
    high = _point(db, goal, "高掌握", 1.0)
    _mastery(db, user, low, 0.05)
    _mastery(db, user, high, 0.99)

    picked = probes_module._pick_points(db, user, goal, "transfer", None, 1)

    assert [point.name for point in picked] == ["低掌握"]


def test_pick_points_challenge_sorts_by_weight(db, db_user_goal):
    user, goal = db_user_goal
    _point(db, goal, "轻量", 1.0)
    heavy = _point(db, goal, "高权重", 3.0)
    _point(db, goal, "中量", 2.0)

    picked = probes_module._pick_points(db, user, goal, "challenge", None, 1)

    assert [point.name for point in picked] == ["高权重"]
    assert picked[0].id == heavy.id


def test_pick_points_respects_kp_id_and_caps_count(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "知识点一", 1.0)
    _point(db, goal, "知识点二", 1.0)
    _point(db, goal, "知识点三", 1.0)
    _point(db, goal, "知识点四", 1.0)

    picked = probes_module._pick_points(db, user, goal, "probe", first.id, 3)
    capped = probes_module._pick_points(db, user, goal, "probe", None, 9)

    assert [point.id for point in picked] == [first.id]
    assert len(capped) == 3


def test_pick_points_unknown_kp_id_falls_back_to_first_point(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "知识点一", 1.0)

    picked = probes_module._pick_points(db, user, goal, "probe", 98765, 1)

    assert [point.id for point in picked] == [first.id]


# --------------------------------------------------------------------------
# 规则出题
# --------------------------------------------------------------------------


def test_rule_questions_generate_four_options_with_matching_answer(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "时态", 2.0)

    questions = probes_module._rule_questions([point], "probe")

    assert len(questions) == 1
    question = questions[0]
    assert question["question"].startswith("探针题")
    assert len(question["options"]) == 4
    assert question["options"][question["answer_index"]] == f"「{point.name}」的核心概念"
    assert question["kp_id"] == point.id
    assert question["kp_name"] == "时态"
    assert "权重 2.0" in question["explanation"]


def test_rule_questions_use_kind_prefix(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "完形填空", 1.0)

    transfer = probes_module._rule_questions([point], "transfer")[0]
    challenge = probes_module._rule_questions([point], "challenge")[0]
    unknown = probes_module._rule_questions([point], "unknown")[0]

    assert transfer["question"].startswith("迁移题")
    assert challenge["question"].startswith("挑战题")
    assert unknown["question"].startswith("题目")


def test_kind_brief_covers_all_valid_kinds():
    assert VALID_KINDS == (
        "probe",
        "transfer",
        "challenge",
        "boundary",
        "speed",
        "reverse",
        "trap",
        "mixed",
    )
    assert set(KIND_BRIEF) == set(VALID_KINDS)


# --------------------------------------------------------------------------
# LLM 出题与结果校验
# --------------------------------------------------------------------------


def test_llm_questions_returns_empty_when_llm_unavailable(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = _point(db, goal, "时态", 1.0)
    monkeypatch.setattr(llm_module.llm, "base_url", "")
    monkeypatch.setattr(llm_module.llm, "api_key", "")

    questions = asyncio.run(probes_module._llm_questions([point], "probe"))

    assert questions == []
    assert llm_module.llm.available is False


def test_llm_questions_normalizes_valid_payload(monkeypatch):
    points = [
        KnowledgePoint(id=1, goal_id=1, name="时态", weight=1.0),
        KnowledgePoint(id=2, goal_id=1, name="从句", weight=1.0),
    ]
    payload = {
        "questions": [
            {
                "question": " Which sentence correctly uses the present perfect tense? ",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "answer_index": 2,
                "explanation": "解析" * 200,
                "kp_name": "时态",
            },
            {
                "question": " Which clause is a relative clause? ",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "answer_index": 0,
                "explanation": "解析",
                "kp_name": "不存在的知识点",
            },
        ]
    }
    _enable_llm(monkeypatch, payload)

    questions = asyncio.run(probes_module._llm_questions(points, "transfer"))

    assert [item["question"] for item in questions] == ["Which sentence correctly uses the present perfect tense?", "Which clause is a relative clause?"]
    assert questions[0]["answer_index"] == 2
    assert questions[0]["kp_id"] == 1
    assert len(questions[0]["explanation"]) == 200
    # kp_name 无法匹配时按顺序回退到 points 中的知识点
    assert questions[1]["kp_id"] == 2
    assert questions[1]["kp_name"] == "从句"


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-dict",
        {"questions": "oops"},
        {"questions": [{"question": "", "options": ["A", "B", "C", "D"], "answer_index": 0}]},
        {"questions": [{"question": "题", "options": ["A", "B", "C"], "answer_index": 0}]},
        {"questions": [{"question": "题", "options": ["A", "B", "C", "D"], "answer_index": 9}]},
        {"questions": [{"question": "题", "options": ["A", "B", "C", "D"], "answer_index": 3.5}]},
        {"questions": ["not-a-dict"]},
    ],
)
def test_llm_questions_skips_invalid_items(monkeypatch, payload):
    points = [KnowledgePoint(id=1, goal_id=1, name="时态", weight=1.0)]
    _enable_llm(monkeypatch, payload)

    questions = asyncio.run(probes_module._llm_questions(points, "probe"))

    assert questions == []


def test_llm_questions_rejects_non_integer_answer_index(monkeypatch):
    points = [KnowledgePoint(id=1, goal_id=1, name="时态", weight=1.0)]
    _enable_llm(
        monkeypatch,
        {
            "questions": [
                {"question": "题", "options": ["A", "B", "C", "D"], "answer_index": "0"}
            ]
        },
    )

    questions = asyncio.run(probes_module._llm_questions(points, "probe"))

    assert questions == []


def test_llm_questions_truncates_long_options(monkeypatch):
    points = [KnowledgePoint(id=1, goal_id=1, name="时态", weight=1.0)]
    _enable_llm(
        monkeypatch,
        {
            "questions": [
                {
                    "question": "Which option is correct?",
                    "options": ["x" * 200, "Option B", "Option C", "Option D"],
                    "answer_index": 0,
                    "explanation": "解析",
                    "kp_name": "时态",
                }
            ]
        },
    )

    questions = asyncio.run(probes_module._llm_questions(points, "probe"))

    assert len(questions[0]["options"][0]) == 120


# --------------------------------------------------------------------------
# 生成探针
# --------------------------------------------------------------------------


def test_generate_probes_rejects_unknown_kind(db, db_user_goal):
    user, goal = db_user_goal
    _point(db, goal, "时态", 1.0)
    db.commit()

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(generate_probes(db, user, goal, kind="invalid"))

    assert str(excinfo.value) == "探针类型必须是 probe / transfer / challenge"


def test_generate_probes_requires_knowledge_points(db, db_user_goal):
    user, goal = db_user_goal

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(generate_probes(db, user, goal))

    assert str(excinfo.value) == "还没有知识点，请先导入资料"


def test_generate_probes_rule_engine_persists_items_and_evidence(db, db_user_goal):
    user, goal = db_user_goal
    weak = _point(db, goal, "薄弱点", 1.0)
    strong = _point(db, goal, "已掌握", 1.0)
    _mastery(db, user, weak, 0.0)
    _mastery(db, user, strong, 0.9)
    db.commit()

    items = asyncio.run(generate_probes(db, user, goal, kind="probe", count=2))

    assert len(items) == 2
    assert [item.status for item in items] == ["pending", "pending"]
    assert [item.kp_id for item in items] == [weak.id, strong.id]
    assert all(json.loads(item.options)[item.answer_index] for item in items)
    assert all(item.user_id == user.id and item.goal_id == goal.id for item in items)

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "probe_generate")).one()
    payload = json.loads(evidence.payload)
    assert evidence.engine == "rule"
    assert payload["points"] == ["薄弱点", "已掌握"]
    assert payload["count"] == 2
    assert payload["kind"] == "probe"
    assert evidence.output == "生成 2 道" + KIND_BRIEF["probe"][:12] + "题"


def test_generate_probes_challenge_prefers_high_weight(db, db_user_goal):
    user, goal = db_user_goal
    _point(db, goal, "轻量", 1.0)
    heavy = _point(db, goal, "重难点", 3.0)
    db.commit()

    items = asyncio.run(generate_probes(db, user, goal, kind="challenge", count=1))

    assert len(items) == 1
    assert items[0].kp_id == heavy.id
    assert "反脆弱" in KIND_BRIEF["challenge"]


def test_generate_probes_caps_count_and_keeps_kp_id_target(db, db_user_goal):
    user, goal = db_user_goal
    target = _point(db, goal, "目标知识点", 1.0)
    for index in range(4):
        _point(db, goal, "备用知识点%s" % index, 1.0)
    db.commit()

    items = asyncio.run(generate_probes(db, user, goal, kind="probe", count=5, kp_id=target.id))

    assert len(items) == 1
    assert items[0].kp_id == target.id


def test_generate_probes_uses_llm_questions_when_valid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = _point(db, goal, "时态", 1.0)
    db.commit()
    _enable_llm(
        monkeypatch,
        {
            "questions": [
                {
                    "question": "He ____ in Beijing since 2018.",
                    "options": ["lives", "lived", "has lived", "is living"],
                    "answer_index": 2,
                    "explanation": "since 2018 提示现在完成时。",
                    "kp_name": "时态",
                }
            ]
        },
    )

    items = asyncio.run(generate_probes(db, user, goal, kind="probe", count=1))

    assert len(items) == 1
    assert items[0].question == "He ____ in Beijing since 2018."
    assert items[0].answer_index == 2
    assert items[0].kp_id == point.id
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "probe_generate")).one()
    assert evidence.engine == "llm"


def test_generate_probes_falls_back_to_rules_when_llm_output_invalid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _point(db, goal, "时态", 1.0)
    db.commit()
    _enable_llm(monkeypatch, {"questions": [{"question": ""}]})

    items = asyncio.run(generate_probes(db, user, goal, kind="probe", count=1))

    assert len(items) == 1
    assert items[0].question.startswith("探针题")
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "probe_generate")).one()
    assert evidence.engine == "rule"


# --------------------------------------------------------------------------
# 作答判分
# --------------------------------------------------------------------------


def test_submit_probe_correct_answer_updates_mastery(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "时态", 1.0)
    _mastery(db, user, point, 0.0)
    probe = _probe(db, user, goal, point, answer_index=2)
    db.commit()

    result = submit_probe(db, user, goal, probe, chosen=2)

    assert result["correct"] is True
    assert result["explanation"] == "解析"
    assert result["mastery"] == 0.08
    assert result["resilience"] == 2
    assert result["evidence"] == "已写入学习证据链"
    assert probe.status == "answered"
    assert probe.chosen_index == 2
    assert probe.correct is True
    assert isinstance(probe.answered_at, datetime)

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "probe_answer")).one()
    payload = json.loads(evidence.payload)
    assert payload["chosen"] == 2
    assert payload["correct_index"] == 2
    assert payload["options"] == ["A", "B", "C", "D"]
    assert payload["kind"] == "probe"
    assert payload["correct"] is True
    assert evidence.output == "回答正确"


def test_submit_probe_wrong_answer_lowers_mastery(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "时态", 1.0)
    _mastery(db, user, point, 0.9)
    probe = _probe(db, user, goal, point, answer_index=1)
    db.commit()

    result = submit_probe(db, user, goal, probe, chosen=0)

    assert result["correct"] is False
    assert result["mastery"] == 0.6714
    assert result["resilience"] == 0
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "probe_answer")).one()
    assert evidence.output == "回答错误，已记录为盲区证据"


def test_submit_probe_rejects_answered_item(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "时态", 1.0)
    probe = _probe(db, user, goal, point, status="answered")
    db.commit()

    with pytest.raises(ValueError) as excinfo:
        submit_probe(db, user, goal, probe, chosen=0)

    assert str(excinfo.value) == "这道题已经作答"


def test_submit_challenge_does_not_penalize_mastery(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "高难阅读", 2.0)
    _mastery(db, user, point, 0.8)
    probe = _probe(db, user, goal, point, answer_index=0, kind="challenge")
    db.commit()

    wrong = submit_probe(db, user, goal, probe, chosen=3)

    assert wrong["correct"] is False
    assert wrong["mastery"] == 0.8
    assert wrong["resilience"] == 1
    stored = db.scalars(select(Mastery).where(Mastery.kp_id == point.id)).one()
    assert stored.value == 0.8

    another = _probe(db, user, goal, point, answer_index=0, kind="challenge")
    db.commit()
    right = submit_probe(db, user, goal, another, chosen=0)
    assert right["correct"] is True
    assert right["mastery"] == 0.8
    assert right["resilience"] == 2


def test_submit_challenge_without_mastery_record_reports_zero(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "陌生概念", 1.0)
    probe = _probe(db, user, goal, point, answer_index=0, kind="challenge")
    db.commit()

    result = submit_probe(db, user, goal, probe, chosen=3)

    assert result["mastery"] == 0.0
    assert result["resilience"] == 1


def test_submit_probe_without_kp_returns_none_mastery(db, db_user_goal):
    user, goal = db_user_goal
    probe = _probe(db, user, goal, None, answer_index=0)
    db.commit()

    result = submit_probe(db, user, goal, probe, chosen=1)

    assert result["correct"] is False
    assert result["mastery"] is None
    assert result["resilience"] == 0


def test_submit_probe_with_missing_point_returns_none_mastery(db, db_user_goal):
    user, goal = db_user_goal
    probe = _probe(db, user, goal, None, answer_index=0)
    probe.kp_id = 99999
    db.commit()

    result = submit_probe(db, user, goal, probe, chosen=0)

    assert result["correct"] is True
    assert result["mastery"] is None
    assert result["resilience"] == 0


def test_submit_probe_tolerates_broken_options_json(db, db_user_goal):
    user, goal = db_user_goal
    probe = _probe(db, user, goal, None, answer_index=0)
    probe.options = "{broken"
    db.commit()

    result = submit_probe(db, user, goal, probe, chosen=1)

    assert result["correct"] is False
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "probe_answer")).one()
    assert json.loads(evidence.payload)["options"] == []


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------


def test_probe_to_dict_includes_point_name(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "写作", 1.5)
    probe = _probe(db, user, goal, point, answer_index=1)
    db.commit()

    data = probe_to_dict(probe, {point.id: point})

    assert data["id"] == probe.id
    assert data["kp_name"] == "写作"
    assert data["options"] == ["A", "B", "C", "D"]
    assert data["status"] == "pending"
    assert data["correct"] is None


def test_probe_to_dict_handles_broken_options_and_missing_point(db, db_user_goal):
    user, goal = db_user_goal
    probe = _probe(db, user, goal, None)
    probe.options = "not-json"
    db.commit()

    data = probe_to_dict(probe, {})

    assert data["options"] == []
    assert data["kp_name"] is None