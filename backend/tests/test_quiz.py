"""AI 随堂测单元测试：规则出题、LLM 出题容错、判分与重排。

所有用例都不得触发真实 DeepSeek 调用：conftest 已清空 LLM 配置，
这里再用 FakeLLM 与 HTTP 客户端哨兵做双重防护。
"""

import asyncio

from unittest.mock import Mock

import pytest

import app.llm as llm_module
import app.services.quiz as quiz_module
from app.cache import cache
from app.models import KnowledgePoint, Mastery, Mistake
from app.services.quiz import (
    _goal_points,
    _llm_questions,
    _rule_questions,
    generate_quiz,
    grade_quiz,
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
    key = f"quiz:{user.id}:{quiz_id}"
    cache.set_json(
        key,
        {"goal_id": goal_id, "questions": questions, "engine": engine},
        ttl=1800,
    )
    return key


# --------------------------------------------------------------------------
# _goal_points / _rule_questions
# --------------------------------------------------------------------------


def test_goal_points_returns_leaves_only(db, db_user_goal):
    user, goal = db_user_goal
    parent = KnowledgePoint(goal_id=goal.id, name="阅读", weight=2.0)
    db.add(parent)
    db.flush()
    child = KnowledgePoint(goal_id=goal.id, name="仔细阅读", weight=1.0, parent_id=parent.id)
    db.add(child)
    db.commit()

    points = _goal_points(db, goal.id)

    assert [point.id for point in points] == [child.id]


def test_rule_questions_build_parent_module_options(db, db_user_goal):
    user, goal = db_user_goal
    parent = KnowledgePoint(goal_id=goal.id, name="阅读", weight=2.0)
    sibling = KnowledgePoint(goal_id=goal.id, name="听力", weight=1.0)
    db.add_all([parent, sibling])
    db.flush()
    child = KnowledgePoint(goal_id=goal.id, name="选词填空", weight=1.5, parent_id=parent.id)
    db.add(child)
    db.commit()

    questions = _rule_questions([child], [parent, sibling, child])

    assert len(questions) == 1
    item = questions[0]
    assert item["question"] == "「选词填空」属于下列哪个学习模块？"
    assert set(item["options"]) == {"阅读", "听力", "基础模块 1", "基础模块 2"}
    assert item["options"][item["answer_index"]] == "阅读"
    assert item["kp_id"] == child.id
    assert item["kp_name"] == "选词填空"
    assert "「选词填空」属于「阅读」" in item["explanation"]
    assert "权重 1.5" in item["explanation"]


def test_rule_questions_without_parent_uses_core_module(db, db_user_goal):
    user, goal = db_user_goal
    point = KnowledgePoint(goal_id=goal.id, name="写作", weight=1.0)
    db.add(point)
    db.commit()

    item = _rule_questions([point], [point])[0]

    assert item["options"][item["answer_index"]] == "核心模块"
    assert set(item["options"]) == {"核心模块", "写作", "基础模块 1", "基础模块 2"}
    assert item["explanation"].startswith("「写作」属于「核心模块」")


def test_rule_questions_caps_distractors_at_three(db, db_user_goal):
    user, goal = db_user_goal
    parents = [
        KnowledgePoint(goal_id=goal.id, name=f"模块{i}", weight=1.0) for i in range(5)
    ]
    db.add_all(parents)
    db.flush()
    child = KnowledgePoint(goal_id=goal.id, name="子知识点", weight=1.0, parent_id=parents[0].id)
    db.add(child)
    db.commit()

    item = _rule_questions([child], parents + [child])[0]

    assert len(item["options"]) == 4
    assert item["options"][item["answer_index"]] == "模块0"
    assert "模块4" not in item["options"]


# --------------------------------------------------------------------------
# _llm_questions
# --------------------------------------------------------------------------


def test_llm_questions_falls_back_when_unavailable(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    fake = FakeLLM(available=False)
    monkeypatch.setattr(quiz_module, "llm", fake)

    questions, engine = _run(_llm_questions([point], [point], 3))

    assert engine == "rule"
    assert len(questions) == 1
    assert questions[0]["kp_id"] == point.id
    assert fake.calls == []


def test_llm_questions_accepts_valid_payload(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力", "阅读"))
    payload = {
        "questions": [
            _question(points[0].id, "听力", 2),
            _question(points[1].id, "阅读", 1),
        ]
    }
    fake = FakeLLM(available=True, payload=payload)
    monkeypatch.setattr(quiz_module, "llm", fake)

    questions, engine = _run(_llm_questions(points, points, 2))

    assert engine == "llm"
    assert len(questions) == 2
    assert [item["kp_id"] for item in questions] == [points[0].id, points[1].id]
    assert [item["kp_name"] for item in questions] == ["听力", "阅读"]
    assert len(fake.calls) == 1
    assert "出题助手" in fake.calls[0]["system"]
    assert "只输出 JSON" in fake.calls[0]["system"]
    assert "听力、阅读" in fake.calls[0]["user"]
    assert "生成 2 道题" in fake.calls[0]["user"]


def test_llm_questions_skips_invalid_items(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力", "阅读"))
    payload = {
        "questions": [
            "不是字典",
            _question(points[0].id, "听力", 0),
            _question(points[0].id, "听力", 0, options=["Option A", "Option B", "Option C"]),
            _question(points[0].id, "听力", 4),
            _question(points[0].id, "听力", "1"),
            _question(points[0].id, "听力", 0, question="   "),
            _question(points[1].id, "未知知识点", 3),
        ]
    }
    fake = FakeLLM(available=True, payload=payload)
    monkeypatch.setattr(quiz_module, "llm", fake)

    questions, engine = _run(_llm_questions(points, points, 7))

    assert engine == "llm"
    assert len(questions) == 2
    assert questions[0]["kp_id"] == points[0].id
    # 未知 kp_name 按顺序回填到下一个知识点
    assert questions[1]["kp_id"] == points[1].id
    assert questions[1]["kp_name"] == "阅读"


def test_llm_questions_falls_back_when_all_items_invalid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    fake = FakeLLM(
        available=True,
        payload={"questions": [{"question": "", "options": ["a"], "answer_index": 0}]},
    )
    monkeypatch.setattr(quiz_module, "llm", fake)

    questions, engine = _run(_llm_questions([point], [point], 1))

    assert engine == "rule"
    assert questions[0]["kp_id"] == point.id


@pytest.mark.parametrize(
    "payload",
    [None, "纯文本", {"foo": "bar"}, {"questions": "not-a-list"}],
)
def test_llm_questions_falls_back_for_malformed_payload(db, db_user_goal, monkeypatch, payload):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, engine = _run(_llm_questions([point], [point], 1))

    assert engine == "rule"
    assert len(questions) == 1


def test_llm_questions_truncates_long_fields(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    long_options = ["x" * 200, "Option B", "Option C", "Option D"]
    payload = {
        "questions": [
            _question(point.id, "听力", 0, options=long_options, explanation="解" * 800)
        ]
    }
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, engine = _run(_llm_questions([point], [point], 1))

    assert engine == "llm"
    assert len(questions[0]["options"][0]) == 120
    assert len(questions[0]["explanation"]) == 600


def test_llm_questions_respects_count(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    payload = {"questions": [_question(point.id, "听力", 0) for _ in range(5)]}
    monkeypatch.setattr(quiz_module, "llm", FakeLLM(available=True, payload=payload))

    questions, engine = _run(_llm_questions([point], [point], 2))

    assert engine == "llm"
    assert len(questions) == 2


# --------------------------------------------------------------------------
# generate_quiz
# --------------------------------------------------------------------------


def test_generate_quiz_without_points_raises(db, db_user_goal):
    user, goal = db_user_goal
    with pytest.raises(ValueError, match="还没有知识点，请先导入资料"):
        _run(generate_quiz(db, user, goal, None, 3))


def test_generate_quiz_rejects_unknown_kp_id(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal, names=("听力",))
    with pytest.raises(ValueError, match="知识点不存在"):
        _run(generate_quiz(db, user, goal, 99999, 3))


def test_generate_quiz_attributes_questions_to_selected_parent_point(db, db_user_goal):
    """选父模块「阅读」时，题目标签必须是「阅读」。

    父模块自己有题库（阅读有篇章题）时不能拆成子知识点出题——否则用户选「阅读」，
    题卡上却写着「仔细阅读 / 选词填空」，考点和题目对不上。
    """
    user, goal = db_user_goal
    parent = KnowledgePoint(goal_id=goal.id, name="阅读", weight=2.0)
    db.add(parent)
    db.flush()
    child = KnowledgePoint(goal_id=goal.id, name="仔细阅读", weight=1.0, parent_id=parent.id)
    db.add(child)
    db.commit()

    result = _run(generate_quiz(db, user, goal, parent.id, 3))
    assert {q["kp_name"] for q in result["questions"]} == {"阅读"}
    assert len(result["questions"]) >= 1


def test_generate_quiz_rejects_unknown_kp_id(db, db_user_goal):
    user, goal = db_user_goal
    parent = KnowledgePoint(goal_id=goal.id, name="口语", weight=2.0)
    db.add(parent)
    db.commit()

    with pytest.raises(ValueError, match="知识点不存在"):
        _run(generate_quiz(db, user, goal, 987654, 3))


def test_generate_quiz_rejects_zero_count(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal, names=("听力",))
    db.commit()

    with pytest.raises(ValueError, match="没有可用知识点"):
        _run(generate_quiz(db, user, goal, None, 0))


def test_generate_quiz_selects_weakest_points_and_hides_answers(db, db_user_goal):
    user, goal = db_user_goal
    strong = KnowledgePoint(goal_id=goal.id, name="已掌握", weight=1.0)
    weak = KnowledgePoint(goal_id=goal.id, name="薄弱", weight=1.0)
    middle = KnowledgePoint(goal_id=goal.id, name="待巩固", weight=3.0)
    db.add_all([strong, weak, middle])
    db.flush()
    db.add_all(
        [
            Mastery(user_id=user.id, kp_id=strong.id, value=0.9),
            Mastery(user_id=user.id, kp_id=weak.id, value=0.1),
            Mastery(user_id=user.id, kp_id=middle.id, value=0.5),
        ]
    )
    db.commit()

    result = _run(generate_quiz(db, user, goal, None, 2))

    assert result["engine"] in {"rule", "bank"}
    assert len(result["questions"]) == 2
    payload = cache.get_json(f"quiz:{user.id}:{result['quiz_id']}")
    assert payload["goal_id"] == goal.id
    assert payload["engine"] == "rule"
    assert [item["kp_id"] for item in payload["questions"]] == [weak.id, middle.id]
    for index, item in enumerate(result["questions"]):
        assert item["index"] == index
        assert "answer_index" not in item
        assert "explanation" not in item
        assert len(item["options"]) == 4


def test_generate_quiz_targets_single_kp(db, db_user_goal):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力", "阅读", "写作"))
    db.commit()

    result = _run(generate_quiz(db, user, goal, points[1].id, 3))

    assert len(result["questions"]) >= 1
    assert result["questions"][0]["kp_id"] == points[1].id
    assert result["questions"][0]["kp_name"] == "阅读"


def test_generate_quiz_uses_llm_engine_when_available(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("量子力学",))[0]
    db.commit()
    # 出题优先走在线/模型，且会多要 1 题进缓存供轮换，因此一次返回 2 题
    payload = {
        "questions": [
            {
                "question": "波函数 ψ(x)=Ae^(ikx) 中的 k 对应下列哪个物理量？",
                "options": ["动量", "能量", "位置", "自旋"],
                "answer_index": 0,
                "explanation": "平面波波矢 k 与动量 p=ℏk 对应。",
                "kp_name": "量子力学",
            },
            {
                "question": "一维无限深势阱中基态的能量随势阱宽度如何变化？",
                "options": ["与宽度平方成反比", "与宽度成正比", "与宽度无关", "与宽度三次方成反比"],
                "answer_index": 0,
                "explanation": "E₁ ∝ 1/L²。",
                "kp_name": "量子力学",
            },
        ]
    }
    fake = FakeLLM(available=True, payload=payload)
    monkeypatch.setattr(quiz_module, "llm", fake)

    result = _run(generate_quiz(db, user, goal, None, 1))

    assert result["engine"] == "llm"
    assert result["questions"][0]["kp_name"] == "量子力学"
    assert len(fake.calls) == 1
    stored = cache.get_json(f"quiz:{user.id}:{result['quiz_id']}")
    assert stored["engine"] == "llm"


def test_generate_quiz_never_touches_network_when_llm_disabled(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    add_points(db, goal, names=("听力",))
    db.commit()
    sentinel = Mock(side_effect=AssertionError("测试禁止创建真实 HTTP 客户端"))
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", sentinel)

    result = _run(generate_quiz(db, user, goal, None, 3))

    assert result["engine"] in {"rule", "bank"}
    assert llm_module.llm.available is False
    sentinel.assert_not_called()


# --------------------------------------------------------------------------
# grade_quiz
# --------------------------------------------------------------------------


def test_grade_quiz_rejects_expired_quiz(db, db_user_goal):
    user, goal = db_user_goal
    with pytest.raises(ValueError, match="题目已过期，请重新生成"):
        grade_quiz(db, user, goal, "missing", [0])


def test_grade_quiz_rejects_quiz_of_another_goal(db, db_user_goal):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    _store_payload(user, "foreign", goal.id + 1, [_question(point.id, point.name, 0)])
    db.commit()

    with pytest.raises(ValueError, match="题目不属于当前目标"):
        grade_quiz(db, user, goal, "foreign", [0])


def test_grade_quiz_all_correct_updates_mastery_without_mistake(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力", "阅读"))
    db.commit()
    replan = Mock(return_value={"changes": []})
    monkeypatch.setattr(quiz_module, "replan", replan)
    key = _store_payload(
        user,
        "perfect",
        goal.id,
        [
            _question(points[0].id, "听力", 1),
            _question(points[1].id, "阅读", 2),
        ],
        engine="llm",
    )

    result = grade_quiz(db, user, goal, "perfect", [1, 2])

    assert result == {
        "score": 100,
        "total": 2,
        "correct": 2,
        "wrong": [],
        # 材料题的交卷原文；本次题目没有材料，因此为空
        "materials": [],
        "replan_changes": [],
        "engine": "llm",
    }
    assert cache.get_json(key) is None
    replan.assert_not_called()
    assert db.query(Mistake).count() == 0
    values = {
        row.kp_id: row.value for row in db.query(Mastery).filter(Mastery.user_id == user.id).all()
    }
    assert values[points[0].id] == 0.08
    assert values[points[1].id] == 0.08



def test_grade_quiz_partial_answers_record_mistake_and_replan(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力", "阅读"))
    db.commit()
    replan = Mock(
        return_value={
            "changes": [
                {"kind": "insert_remedial", "detail": "已插入补救任务", "task_id": 9}
            ]
        }
    )
    monkeypatch.setattr(quiz_module, "replan", replan)
    _store_payload(
        user,
        "partial",
        goal.id,
        [
            _question(points[0].id, "听力", 1),
            _question(points[1].id, "阅读", 2),
        ],
    )

    result = grade_quiz(db, user, goal, "partial", [1])

    assert result["score"] == 50
    assert result["total"] == 2
    assert result["correct"] == 1
    assert result["engine"] in {"rule", "bank"}
    assert len(result["wrong"]) == 1
    wrong = result["wrong"][0]
    assert wrong["index"] == 1
    assert wrong["chosen"] == "未作答"
    assert wrong["correct"] == "Option C"
    assert wrong["category"] == "time"
    assert wrong["category_label"] == "时间不够"
    assert wrong["kp_name"] == "阅读"
    assert result["replan_changes"][0]["kind"] == "insert_remedial"
    replan.assert_called_once_with(db, user.id, goal, trigger="quiz")

    mistakes = db.query(Mistake).all()
    assert len(mistakes) == 1
    assert mistakes[0].source == "quiz"
    assert mistakes[0].kp_id == points[1].id
    assert mistakes[0].question.startswith("Which statement about")
    values = {
        row.kp_id: row.value for row in db.query(Mastery).filter(Mastery.user_id == user.id).all()
    }
    assert values[points[0].id] == 0.08
    assert values[points[1].id] == 0.08


def test_grade_quiz_treats_out_of_range_answer_as_blank(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    db.commit()
    monkeypatch.setattr(quiz_module, "replan", Mock(return_value={"changes": []}))
    _store_payload(user, "out-of-range", goal.id, [_question(point.id, "听力", 2)])

    result = grade_quiz(db, user, goal, "out-of-range", [99])

    assert result["correct"] == 0
    assert result["wrong"][0]["chosen"] == "未作答"
    assert result["wrong"][0]["correct"] == "Option C"


def test_grade_quiz_without_kp_id_skips_mastery_and_mistake(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    replan = Mock(return_value={"changes": [{"kind": "keep", "detail": "无需调整", "task_id": None}]})
    monkeypatch.setattr(quiz_module, "replan", replan)
    _store_payload(
        user,
        "no-kp",
        goal.id,
        [_question(None, "未知知识点", 0)],
    )

    result = grade_quiz(db, user, goal, "no-kp", [3])

    assert result["correct"] == 0
    assert result["wrong"][0]["kp_name"] == "未知知识点"
    assert db.query(Mistake).count() == 0
    assert db.query(Mastery).count() == 0
    replan.assert_called_once_with(db, user.id, goal, trigger="quiz")


def test_grade_quiz_with_empty_questions_returns_zero(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    replan = Mock(return_value={"changes": []})
    monkeypatch.setattr(quiz_module, "replan", replan)
    _store_payload(user, "empty", goal.id, [])

    result = grade_quiz(db, user, goal, "empty", [])

    assert result["score"] == 0
    assert result["total"] == 0
    assert result["correct"] == 0
    assert result["wrong"] == []
    replan.assert_not_called()


def test_grade_quiz_defaults_engine_to_rule(db, db_user_goal):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    db.commit()
    cache.set_json(
        f"quiz:{user.id}:legacy",
        {"goal_id": goal.id, "questions": [_question(point.id, "听力", 0)]},
        ttl=1800,
    )

    result = grade_quiz(db, user, goal, "legacy", [0])

    assert result["engine"] in {"rule", "bank"}
    assert result["score"] == 100


# --------------------------------------------------------------------------
# API：/goals/{id}/quiz/generate 与 /submit
# --------------------------------------------------------------------------


def test_quiz_api_generate_and_submit_all_correct(api, auth, goal, imported_points):
    token = auth["token"]
    generated = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/generate",
        token=token,
        json={"count": 3},
    )

    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["engine"] in {"rule", "bank"}
    assert len(body["questions"]) >= 2
    for index, question in enumerate(body["questions"]):
        assert question["index"] == index
        assert len(question["options"]) == 4
        assert "answer_index" not in question
        assert "explanation" not in question

    payload = cache.get_json(f"quiz:{auth['user']['id']}:{body['quiz_id']}")
    answers = [item["answer_index"] for item in payload["questions"]]
    submitted = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/submit",
        token=token,
        json={"quiz_id": body["quiz_id"], "answers": answers},
    )

    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["score"] == 100
    assert result["correct"] == len(body["questions"])
    assert result["total"] == len(body["questions"])
    assert result["wrong"] == []
    assert result["engine"] in {"rule", "bank"}

    again = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/submit",
        token=token,
        json={"quiz_id": body["quiz_id"], "answers": answers},
    )
    assert again.status_code == 400
    assert again.json()["detail"] == "题目已过期，请重新生成"


def test_quiz_api_submit_all_wrong_records_mistakes(api, auth, goal, imported_points):
    token = auth["token"]
    body = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/generate",
        token=token,
        json={"count": 2},
    ).json()
    payload = cache.get_json(f"quiz:{auth['user']['id']}:{body['quiz_id']}")
    wrong_answers = [(item["answer_index"] + 1) % 4 for item in payload["questions"]]

    result = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/submit",
        token=token,
        json={"quiz_id": body["quiz_id"], "answers": wrong_answers},
    ).json()

    assert result["score"] == 0
    assert result["correct"] == 0
    assert len(result["wrong"]) == 2
    assert all(item["chosen"] != item["correct"] for item in result["wrong"])
    assert all(item["category"] for item in result["wrong"])
    assert isinstance(result["replan_changes"], list)

    mistakes = api("GET", f"/api/goals/{goal['id']}/mistakes", token=token)
    assert mistakes.status_code == 200
    assert len(mistakes.json()) == 2


def test_quiz_api_rejects_unknown_quiz_id(api, auth, goal, imported_points):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/submit",
        token=auth["token"],
        json={"quiz_id": "not-exists", "answers": [0]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "题目已过期，请重新生成"


def test_quiz_api_generate_without_points(api, auth, goal):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/generate",
        token=auth["token"],
        json={"count": 3},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "还没有知识点，请先导入资料"


def test_quiz_api_generate_rejects_unknown_kp(api, auth, goal, imported_points):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/generate",
        token=auth["token"],
        json={"kp_id": 99999, "count": 1},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "知识点不存在"


def test_quiz_api_validates_count(api, auth, goal, imported_points):
    token = auth["token"]
    for invalid in (0, 7):
        response = api(
            "POST",
            f"/api/goals/{goal['id']}/quiz/generate",
            token=token,
            json={"count": invalid},
        )
        assert response.status_code == 422


def test_quiz_api_requires_authentication(api, goal):
    assert api("POST", f"/api/goals/{goal['id']}/quiz/generate", json={"count": 1}).status_code == 401
    assert (
        api(
            "POST",
            f"/api/goals/{goal['id']}/quiz/submit",
            json={"quiz_id": "x", "answers": []},
        ).status_code
        == 401
    )


def test_quiz_api_rejects_unknown_goal(api, auth):
    assert (
        api(
            "POST",
            "/api/goals/99999/quiz/generate",
            token=auth["token"],
            json={"count": 1},
        ).status_code
        == 404
    )