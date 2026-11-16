"""材料型题目（阅读理解 / 听力理解）单元测试。

要点：阅读必须给完整文章、听力只给音频脚本不给可读正文、
材料太短或题量不足要回落、答案位置不能恒为 A。
"""

import asyncio

import app.services.quiz as quiz_module
from app.services import quiz_material
from app.services.quiz import _llm_material_set, generate_quiz, grade_quiz
from tests.conftest import add_points


def _run(coro):
    return asyncio.run(coro)


class FakeLLM:
    """支持 max_tokens 关键字，避免打桩签名与真实客户端不一致。"""

    def __init__(self, available=True, payload=None, payloads=None):
        self.available = available
        self.payload = payload
        self.payloads = list(payloads or [])
        self.calls = []

    async def chat_json(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, "kwargs": kwargs})
        if self.payloads:
            return self.payloads.pop(0)
        return self.payload


def _passage(words=180):
    body = " ".join(f"word{i}" for i in range(words - 12))
    return (
        "Remote work has changed how teams operate. "
        "It brings flexibility but also blurs the line between work and rest. "
        + body
    )


def _listening(words=120):
    body = " ".join(f"talk{i}" for i in range(words - 16))
    return "W: Did you finish the report? M: Not yet, I need one more day. " + body


def _material_payload(kind="passage", count=2, answer_index=0):
    if kind == "listening":
        material = {"title": "A Short Conversation", "audio_script": _listening()}
    else:
        material = {"title": "Remote Work", "content": _passage()}
    questions = []
    for index in range(count):
        questions.append(
            {
                "question": f"What can be inferred from the material (item {index})?",
                "options": ["Alpha", "Beta", "Gamma", "Delta"],
                "answer_index": answer_index,
                "explanation": "解析",
                "kp_name": "阅读",
                "option_reasons": ["", "混淆", "遗漏", "过度推断"],
                "distractor_causes": [None, "concept", "method", "careless"],
            }
        )
    return {"material": material, "questions": questions}


class _Goal:
    exam_name = "大学英语四级（CET-4）"
    id = 1


def test_material_kind_detects_reading_and_listening():
    assert quiz_material.material_kind(["阅读"], "大学英语四级（CET-4）") == "passage"
    assert quiz_material.material_kind(["长篇阅读"], "大学英语四级（CET-4）") == "passage"
    assert quiz_material.material_kind(["听力"], "大学英语四级（CET-4）") == "listening"
    assert quiz_material.material_kind(["短对话"], "大学英语四级（CET-4）") == "listening"
    # 纯数学知识点不出材料题
    assert quiz_material.material_kind(["定积分"], "高等数学") is None
    # 听力 + 阅读混选：按数量多的一类走，不同时出两种材料
    assert quiz_material.material_kind(["短对话", "长对话", "阅读"], "CET-4") == "listening"


def test_parse_material_rejects_too_short():
    assert quiz_material.parse_material({"content": "too short"}, "passage") is None
    assert quiz_material.parse_material({"audio_script": "hi"}, "listening") is None
    ok = quiz_material.parse_material({"content": _passage()}, "passage")
    assert ok and ok["kind"] == "passage"
    assert ok["word_count"] >= quiz_material.MIN_PASSAGE_WORDS


def test_public_material_hides_listening_text():
    """听力材料不能把可读原文直接发给前端，否则就变成阅读题了。"""
    material = quiz_material.parse_material({"audio_script": _listening()}, "listening")
    material["id"] = "m1"
    view = quiz_material.public_material(material)
    assert view["kind"] == "listening"
    assert view["audio_script"]
    assert "content" not in view

    passage = quiz_material.parse_material({"content": _passage()}, "passage")
    passage["id"] = "m2"
    view2 = quiz_material.public_material(passage)
    assert view2["kind"] == "passage"
    assert view2["content"]


def test_material_set_attaches_material_and_shuffles_options(monkeypatch):
    points = [type("P", (), {"id": 7, "name": "阅读"})()]
    fake = FakeLLM(payload=_material_payload("passage", count=2, answer_index=0))
    monkeypatch.setattr(quiz_module, "llm", fake)

    items = _run(_llm_material_set(points, points, 2, _Goal(), "passage"))

    assert len(items) == 2
    for item in items:
        assert item["material"]["kind"] == "passage"
        assert item["material"]["id"]
        assert item["material"]["word_count"] >= 150
        # 选项数量与错因数量保持一致，判分口径不变
        assert len(item["options"]) == 4
        assert len(item["distractor_causes"]) == 4
        assert item["distractor_causes"][item["answer_index"]] is None
    # 答案位置被打散：两道题的答案不能都停在原位（原答案都是 0）
    assert any(item["answer_index"] != 0 for item in items)
    # 请求必须放宽 max_tokens，否则文章会被截断
    assert fake.calls[0]["kwargs"].get("max_tokens", 0) >= 2000


def test_material_set_rejects_invalid_material(monkeypatch):
    points = [type("P", (), {"id": 7, "name": "阅读"})()]
    fake = FakeLLM(payload={"material": {"content": "tiny"}, "questions": []})
    monkeypatch.setattr(quiz_module, "llm", fake)
    assert _run(_llm_material_set(points, points, 2, _Goal(), "passage")) == []

    fake2 = FakeLLM(payload=None)
    monkeypatch.setattr(quiz_module, "llm", fake2)
    assert _run(_llm_material_set(points, points, 2, _Goal(), "passage")) == []


def test_material_set_tops_up_missing_questions(monkeypatch):
    points = [type("P", (), {"id": 7, "name": "阅读"})()]
    first = _material_payload("passage", count=2, answer_index=1)
    top_up = _material_payload("passage", count=1, answer_index=2)
    top_up["questions"][0]["question"] = "A brand new question about the same passage?"
    fake = FakeLLM(payloads=[first, top_up])
    monkeypatch.setattr(quiz_module, "llm", fake)

    items = _run(_llm_material_set(points, points, 3, _Goal(), "passage"))
    assert len(items) == 3
    # 续出的题必须挂在同一份材料下
    assert len({item["material"]["id"] for item in items}) == 1


def test_generate_quiz_uses_material_for_reading(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    goal.exam_name = "大学英语四级（CET-4）"
    db.commit()
    add_points(db, goal, names=("阅读",))
    fake = FakeLLM(payload=_material_payload("passage", count=2, answer_index=0))
    monkeypatch.setattr(quiz_module, "llm", fake)

    result = _run(generate_quiz(db, user, goal, None, 2))
    material = result["questions"][0].get("material")
    assert material and material["kind"] == "passage"
    assert material["content"]
    assert "audio_script" not in material


def test_grade_quiz_returns_transcript_after_submit(db, db_user_goal, monkeypatch):
    """听力原文只在交卷后返回，出卷时不可见。"""
    user, goal = db_user_goal
    goal.exam_name = "大学英语四级（CET-4）"
    db.commit()
    add_points(db, goal, names=("听力",))
    fake = FakeLLM(payload=_material_payload("listening", count=2, answer_index=0))
    monkeypatch.setattr(quiz_module, "llm", fake)

    created = _run(generate_quiz(db, user, goal, None, 2))
    material = created["questions"][0]["material"]
    assert material["kind"] == "listening"
    assert "content" not in material

    graded = grade_quiz(db, user, goal, created["quiz_id"], [0, 0])
    assert len(graded["materials"]) == 1
    assert graded["materials"][0]["transcript"]
