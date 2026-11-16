"""B2 干扰项诊断出题测试：错因绑定、确定性、判题即归因、LLM 非法值拦截。

所有用例都不触发真实 DeepSeek 调用：conftest 已清空 LLM 配置，
这里再用 FakeLLM 做防护。
"""

import asyncio

from unittest.mock import Mock

import pytest

import app.services.quiz as quiz_module
from app.cache import cache
from app.models import KnowledgePoint, Mistake
from app.services.rules import MISTAKE_CATEGORIES
from app.services.quiz import (
    VALID_CAUSES,
    _assign_causes,
    _llm_questions,
    _rule_questions,
    distractor_binding_issues,
    generate_quiz,
    grade_quiz,
    normalize_distractor_cause,
)
from tests.conftest import add_points


def _run(coro):
    return asyncio.run(coro)


class FakeLLM:
    def __init__(self, available=False, payload=None):
        self.available = available
        self.payload = payload
        self.calls = []

    async def chat_json(self, system, user):
        self.calls.append({"system": system, "user": user})
        return self.payload


def _question(kp_id, kp_name, answer_index=1, **overrides):
    item = {
        "question": f"Which statement about {kp_name} is correct?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "answer_index": answer_index,
        "explanation": "解析",
        "kp_name": kp_name,
        "kp_id": kp_id,
    }
    item.update(overrides)
    return item


def _store_payload(user, quiz_id, goal_id, questions, engine="rule"):
    cache.set_json(
        f"quiz:{user.id}:{quiz_id}",
        {"goal_id": goal_id, "questions": questions, "engine": engine},
        ttl=1800,
    )


def _child_tree(db, goal):
    """构造 父模块 + 兄弟模块 + 叶子知识点，让规则路径能凑出 3 个干扰项。"""
    parents = [KnowledgePoint(goal_id=goal.id, name=name, weight=2.0) for name in ("阅读", "听力", "写作", "翻译")]
    db.add_all(parents)
    db.flush()
    child = KnowledgePoint(goal_id=goal.id, name="选词填空", weight=1.5, parent_id=parents[0].id)
    db.add(child)
    db.commit()
    return parents, child


# --------------------------------------------------------------------------
# 规则兜底路径：每个干扰项都绑定合法错因
# --------------------------------------------------------------------------


def test_rule_questions_bind_a_cause_to_every_distractor(db, db_user_goal):
    user, goal = db_user_goal
    _parents, child = _child_tree(db, goal)
    all_points = db.query(KnowledgePoint).filter_by(goal_id=goal.id).all()

    item = _rule_questions([child], all_points)[0]

    causes = item["distractor_causes"]
    assert len(causes) == 4
    # 正确选项不错标
    assert causes[item["answer_index"]] is None
    distractor_causes = [cause for index, cause in enumerate(causes) if index != item["answer_index"]]
    assert len(distractor_causes) == 3
    for cause in distractor_causes:
        assert cause in VALID_CAUSES
    assert distractor_binding_issues(causes) == []
    # 每个被绑定的干扰项都有对应的典型误解文案
    reasons = item["option_reasons"]
    assert reasons[item["answer_index"]] == ""
    for index, cause in enumerate(causes):
        if cause is not None:
            assert reasons[index] and cause in MISTAKE_CATEGORIES


def test_rule_questions_use_all_four_causes_across_points(db, db_user_goal):
    user, goal = db_user_goal
    parents = [KnowledgePoint(goal_id=goal.id, name=f"模块{i}", weight=1.0) for i in range(6)]
    db.add_all(parents)
    db.flush()
    names = ("概念辨析", "公式推导", "审题细节", "听力速度", "定义理解", "计算方法")
    children = [
        KnowledgePoint(goal_id=goal.id, name=name, weight=1.0, parent_id=parents[index].id)
        for index, name in enumerate(names)
    ]
    db.add_all(children)
    db.commit()

    questions = _rule_questions(children, parents + children)

    used = {cause for item in questions for cause in item["distractor_causes"] if cause}
    assert set(VALID_CAUSES) <= used
    for item in questions:
        assert distractor_binding_issues(item["distractor_causes"]) == []


def test_assign_causes_is_keyword_biased_and_covers_four_categories():
    # 特征命中时对应错因必然排在最前（确定性偏置，非随机）
    assert _assign_causes("概念辨析", 3)[0] == "concept"
    assert _assign_causes("公式推导方法", 3)[0] == "method"
    assert _assign_causes("审题细节", 3)[0] == "careless"
    assert _assign_causes("听力速度", 3)[0] == "time"
    assert sorted(set(_assign_causes("任意知识点", 4))) == sorted(VALID_CAUSES)
    assert _assign_causes("任意知识点", 0) == []


def test_assign_causes_primary_bias_holds_for_every_name():
    """命中唯一特征时主错因必须稳居第一位，且不受散列轮转影响。"""
    for name, expected in (
        ("计算方法", "method"),
        ("单位换算", "careless"),
        ("速读技巧", "time"),
        ("概念定义", "concept"),
    ):
        causes = _assign_causes(name, 3)
        assert causes[0] == expected, (name, causes)
        assert len(set(causes)) == 3, (name, causes)


def test_assign_causes_is_stable_across_processes_hash_seed():
    # 不依赖 Python 内置 hash（对 str 加盐），换种子也必须得到同样结果
    first = [_assign_causes(name, 3) for name in ("阅读策略", "虚拟语气", "牛顿定律")]
    second = [_assign_causes(name, 3) for name in ("阅读策略", "虚拟语气", "牛顿定律")]
    assert first == second


# --------------------------------------------------------------------------
# 确定性：同输入两次调用产出完全一致
# --------------------------------------------------------------------------


def test_rule_questions_are_deterministic_for_same_input(db, db_user_goal):
    user, goal = db_user_goal
    _child_tree(db, goal)
    all_points = db.query(KnowledgePoint).filter_by(goal_id=goal.id).all()
    leaves = [point for point in all_points if point.parent_id is not None]

    monkey_no_shuffle = Mock()
    monkey_no_shuffle.shuffle = lambda seq: None
    original_random = quiz_module.random
    try:
        # 打乱顺序由 random 决定；固定为恒等排列后，两次调用必须逐字段相同
        quiz_module.random = monkey_no_shuffle
        first = _rule_questions(leaves, all_points)
        second = _rule_questions(leaves, all_points)
    finally:
        quiz_module.random = original_random

    assert first == second
    for item in first:
        assert item["distractor_causes"][item["answer_index"]] is None


def test_option_to_cause_mapping_survives_shuffled_order(db, db_user_goal):
    """错因按干扰项文本分配，与选项位置无关，因此打乱顺序不会改变诊断口径。"""
    user, goal = db_user_goal
    _child_tree(db, goal)
    all_points = db.query(KnowledgePoint).filter_by(goal_id=goal.id).all()
    child = next(point for point in all_points if point.name == "选词填空")

    def rotate_by(step):
        def apply(seq):
            rotated = seq[step:] + seq[:step]
            seq[:] = rotated

        return apply

    seen = {}
    original_random = quiz_module.random
    try:
        for step in range(4):
            fake = Mock()
            fake.shuffle = rotate_by(step)
            quiz_module.random = fake
            item = _rule_questions([child], all_points)[0]
            for option, cause in zip(item["options"], item["distractor_causes"]):
                if cause is not None:
                    seen.setdefault(option, set()).add(cause)
    finally:
        quiz_module.random = original_random

    assert len(seen) == 3, seen
    assert all(len(causes) == 1 for causes in seen.values()), seen


def test_generate_quiz_is_repeatable(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    add_points(db, goal, names=("概念辨析", "公式推导", "审题细节"))
    db.commit()
    # 固定选项顺序，隔离掉 random.shuffle 后验证错因分配本身可复算
    monkeypatch.setattr(quiz_module.random, "shuffle", lambda seq: None)

    first = _run(generate_quiz(db, user, goal, None, 3))
    second = _run(generate_quiz(db, user, goal, None, 3))

    assert [q["options"] for q in first["questions"]] == [q["options"] for q in second["questions"]]
    assert [q["distractor_causes"] for q in first["questions"]] == [
        q["distractor_causes"] for q in second["questions"]
    ]
    for question in first["questions"]:
        assert sum(1 for cause in question["distractor_causes"] if cause in VALID_CAUSES) == 3


# --------------------------------------------------------------------------
# LLM 路径：解析并校验 distractor_cause
# --------------------------------------------------------------------------


def test_llm_prompt_declares_distractor_cause_contract(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    fake = FakeLLM(available=True, payload={"questions": [_question(point.id, "听力", 0)]})
    monkeypatch.setattr(quiz_module, "llm", fake)

    _run(_llm_questions([point], [point], 1))

    assert "distractor_causes" in fake.calls[0]["system"]
    assert "concept/method/careless/time" in fake.calls[0]["system"]


def test_llm_questions_accepts_valid_distractor_causes(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    payload = {
        "questions": [
            _question(
                point.id,
                "听力",
                1,
                distractor_causes=[None, None, "method", "careless"],
            )
        ]
    }
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, engine = _run(_llm_questions([point], [point], 1))

    assert engine == "llm"
    causes = questions[0]["distractor_causes"]
    assert causes[1] is None  # 正确项不错标
    assert causes[2] == "method"
    assert causes[3] == "careless"
    assert distractor_binding_issues(causes) == []


def test_llm_questions_repairs_illegal_distractor_cause(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    payload = {
        "questions": [
            _question(
                point.id,
                "听力",
                0,
                # 第 2 项是枚举外的幻觉值，第 3 项缺失 —— 都必须被规则修复
                distractor_causes=["astrology", None, "", "not-a-cause"],
            )
        ]
    }
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, engine = _run(_llm_questions([point], [point], 1))

    assert engine == "llm"
    causes = questions[0]["distractor_causes"]
    assert causes[0] is None
    illegal = [c for c in causes[1:] if c not in VALID_CAUSES]
    assert illegal == [], f"非法错因未被拦下: {illegal}"
    assert distractor_binding_issues(causes) == []


def test_llm_questions_parses_cause_with_explanation_prefix(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    payload = {
        "questions": [
            _question(
                point.id,
                "听力",
                2,
                distractor_causes=["concept：把持续动作当成过去", None, "", "TIME：没看清时限"],
            )
        ]
    }
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, _engine = _run(_llm_questions([point], [point], 1))

    causes = questions[0]["distractor_causes"]
    assert causes[2] is None  # 正确项不错标
    assert causes[0] == "concept"
    assert causes[3] == "time"
    assert all(cause in VALID_CAUSES for pos, cause in enumerate(causes) if pos != 2)
    assert distractor_binding_issues(causes) == []


def test_llm_questions_fills_missing_causes_from_rule_mapping(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    payload = {"questions": [_question(point.id, "听力", 3)]}  # 完全没有 distractor_causes
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, _engine = _run(_llm_questions([point], [point], 1))
    expected = _assign_causes(point.name, 4)

    causes = questions[0]["distractor_causes"]
    assert causes[3] is None
    assert [causes[i] for i in range(3)] == [expected[i] for i in range(3)]
    assert distractor_binding_issues(causes) == []


@pytest.mark.parametrize("raw,fallback,expected", [
    ("concept", "method", ("concept", False)),
    ("Method：步骤记混", "concept", ("method", False)),
    ("time", "concept", ("time", False)),
    ("astrology", "method", ("method", True)),
    ("", "careless", ("careless", True)),
    (None, "time", ("time", True)),
])
def test_normalize_distractor_cause(raw, fallback, expected):
    assert normalize_distractor_cause(raw, fallback) == expected


def test_distractor_binding_issues_flags_wrong_labels():
    assert distractor_binding_issues([None, "concept", "method", "careless"]) == []
    issues = distractor_binding_issues(["concept", "magic", None, "time"])
    assert issues and issues[0]["layer"] == "enum"


# --------------------------------------------------------------------------
# 判题即归因：错题自动归类率 100%
# --------------------------------------------------------------------------


def test_grade_quiz_writes_bound_cause_into_mistake(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    db.commit()
    monkeypatch.setattr(quiz_module, "replan", Mock(return_value={"changes": []}))
    _store_payload(
        user,
        "bound",
        goal.id,
        [_question(point.id, "听力", 0, distractor_causes=[None, "method", "careless", "time"])],
    )

    result = grade_quiz(db, user, goal, "bound", [1])

    assert result["correct"] == 0
    wrong = result["wrong"][0]
    assert wrong["category"] == "method"
    assert wrong["category_label"] == MISTAKE_CATEGORIES["method"]
    assert wrong["distractor_cause"] == "method"
    assert wrong["attribution"] == "option_bound"

    mistakes = db.query(Mistake).all()
    assert len(mistakes) == 1
    assert mistakes[0].category == "method"
    assert mistakes[0].category_label == MISTAKE_CATEGORIES["method"]
    assert mistakes[0].distractor_cause == "method"
    assert mistakes[0].source == "quiz"


def test_grade_quiz_overrides_rule_attribution_for_careless_option(db, db_user_goal, monkeypatch):
    """选项绑定优先于规则归因：即便规则会判成别的类别，也按绑定的 careless 记录。"""
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    db.commit()
    monkeypatch.setattr(quiz_module, "replan", Mock(return_value={"changes": []}))
    _store_payload(
        user,
        "careless",
        goal.id,
        [_question(point.id, "听力", 0, options=["求和公式", "单位漏乘", "丙", "丁"],
                   distractor_causes=[None, "careless", "concept", "time"])],
    )

    result = grade_quiz(db, user, goal, "careless", [1])

    assert result["wrong"][0]["category"] == "careless"
    mistake = db.query(Mistake).one()
    assert mistake.category == "careless"
    assert mistake.distractor_cause == "careless"


def test_grade_quiz_auto_classifies_every_distractor(db, db_user_goal, monkeypatch):
    """逐个选错每个干扰项，错因都必须落到四类之一并与绑定一致。"""
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    db.commit()
    monkeypatch.setattr(quiz_module, "replan", Mock(return_value={"changes": []}))
    causes = [None, "concept", "method", "time"]
    _store_payload(
        user,
        "all",
        goal.id,
        [_question(point.id, "听力", 0, distractor_causes=list(causes))],
    )

    classified = []
    labels = ["Option A", "Option B", "Option C", "Option D"]
    for chosen in (1, 2, 3):
        _store_payload(user, f"all-{chosen}", goal.id, [
            _question(point.id, "听力", 0, distractor_causes=list(causes))
        ])
        result = grade_quiz(db, user, goal, f"all-{chosen}", [chosen])
        mistake = db.query(Mistake).filter(Mistake.user_answer == labels[chosen]).one()
        classified.append((result["wrong"][0]["category"], mistake.category, mistake.distractor_cause))

    assert classified == [("concept", "concept", "concept"),
                          ("method", "method", "method"),
                          ("time", "time", "time")]
    # 错题自动归类率 100%：没有任何一条记录的 category 落在四类之外
    rows = db.query(Mistake).all()
    assert rows and all(row.category in VALID_CAUSES for row in rows)
    assert all(row.distractor_cause in VALID_CAUSES for row in rows)


def test_grade_quiz_falls_back_to_rule_for_legacy_questions(db, db_user_goal, monkeypatch):
    """旧缓存里的题没有 distractor_causes，仍按规则归因且 distractor_cause 为空。"""
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    db.commit()
    monkeypatch.setattr(quiz_module, "replan", Mock(return_value={"changes": []}))
    _store_payload(user, "legacy", goal.id, [_question(point.id, "听力", 0)])

    result = grade_quiz(db, user, goal, "legacy", [99])

    assert result["wrong"][0]["category"] == "time"  # 未作答 → 规则判时间不够
    assert result["wrong"][0]["attribution"] == "rule"
    mistake = db.query(Mistake).one()
    assert mistake.category == "time"
    assert mistake.distractor_cause is None


def test_generated_quiz_exposes_causes_but_not_answers(db, db_user_goal):
    user, goal = db_user_goal
    _child_tree(db, goal)
    db.commit()

    result = _run(generate_quiz(db, user, goal, None, 1))

    question = result["questions"][0]
    assert "answer_index" not in question
    assert "explanation" not in question
    assert len(question["options"]) == 4
    assert len(question["distractor_causes"]) == 4
    assert sum(1 for cause in question["distractor_causes"] if cause in VALID_CAUSES) == 3


def test_end_to_end_rule_quiz_fully_auto_classified(db, db_user_goal, monkeypatch):
    """生成 → 全选错 → 每条错题都自动带上四类之一的错因。"""
    user, goal = db_user_goal
    _child_tree(db, goal)
    db.commit()
    monkeypatch.setattr(quiz_module, "replan", Mock(return_value={"changes": []}))

    result = _run(generate_quiz(db, user, goal, None, 1))
    stored = cache.get_json(f"quiz:{user.id}:{result['quiz_id']}")
    question = stored["questions"][0]
    wrong_choice = (question["answer_index"] + 1) % 4

    graded = grade_quiz(db, user, goal, result["quiz_id"], [wrong_choice])

    assert graded["correct"] == 0
    mistake = db.query(Mistake).one()
    bound = question["distractor_causes"][wrong_choice]
    assert bound in VALID_CAUSES
    assert mistake.category == bound
    assert mistake.distractor_cause == bound
    assert graded["wrong"][0]["category"] == bound
