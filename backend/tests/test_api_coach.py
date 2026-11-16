"""语音问答（Coach / qa service）单元测试。"""

import asyncio
from datetime import date, datetime, timedelta

import pytest

from app.models import Goal, KnowledgePoint, Mastery, Mistake, Task, User
from app.services import qa


class _FakeLLM:
    """可控的大模型替身，记录每次调用的参数。"""

    def __init__(self, reply=None, available=True):
        self.reply = reply
        self.available = available
        self.calls = []

    async def chat(self, system, user, temperature=0.2, max_tokens=900):
        self.calls.append((system, user, temperature, max_tokens))
        return self.reply


def _add_point(db, user, goal, name, value):
    point = KnowledgePoint(goal_id=goal.id, name=name, weight=1.0)
    db.add(point)
    db.flush()
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=value))
    db.flush()
    return point


def _add_task(db, user, goal, day, title, status, minutes, priority=1.0):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day,
        title=title,
        status=status,
        duration_min=minutes,
        priority=priority,
    )
    db.add(task)
    return task


# --------------------------------------------------------------------------
# build_rule_answer：每个关键词分支的正向 / 负向路径
# --------------------------------------------------------------------------


def test_build_rule_answer_without_goal(db, db_user_goal):
    user, _ = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, None, "今天学什么")

    assert "你还没有设置考试目标" in answer
    assert "「目标与资料」" in answer
    assert suggestions == ["创建考试目标", "导入学习资料"]


def test_build_rule_answer_countdown_branch(db, db_user_goal):
    user, goal = db_user_goal
    today = goal.exam_date - timedelta(days=12)

    answer, suggestions = qa.build_rule_answer(db, user, goal, "还有几天考试", today=today)

    assert "距离「CET-4」还有 12 天" in answer
    assert "每天可用 90 分钟" in answer
    assert suggestions == ["查看学习计划", "生成周报"]


def test_build_rule_answer_weakest_without_mastery(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "我的薄弱点在哪里")

    assert "还没有掌握度数据" in answer
    assert suggestions == ["导入资料"]


def test_build_rule_answer_weakest_lists_three_in_ascending_order(db, db_user_goal):
    user, goal = db_user_goal
    _add_point(db, user, goal, "写作", 0.9)
    _add_point(db, user, goal, "听力", 0.2)
    _add_point(db, user, goal, "阅读", 0.5)
    _add_point(db, user, goal, "翻译", 0.75)
    db.commit()

    answer, suggestions = qa.build_rule_answer(db, user, goal, "我最差的是哪块", today=date.today())

    assert "听力（20%）" in answer
    assert "阅读（50%）" in answer
    assert "翻译（75%）" in answer
    assert "写作" not in answer
    assert answer.index("听力") < answer.index("阅读") < answer.index("翻译")
    assert suggestions == ["复习 听力", "录入错题"]


def test_build_rule_answer_today_without_tasks(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "我今天要干什么")

    assert "今天还没有排任务" in answer
    assert "「学习计划」" in answer
    assert suggestions == ["生成 7 天计划"]


def test_build_rule_answer_today_counts_pending_only(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _add_task(db, user, goal, today, "背单词", "done", 20, priority=3)
    _add_task(db, user, goal, today, "听力练习", "pending", 30, priority=2)
    _add_task(db, user, goal, today, "跳过任务", "skipped", 50, priority=1)
    db.commit()

    answer, suggestions = qa.build_rule_answer(db, user, goal, "今天学什么", today=today)

    assert "今天共 2 个任务" in answer
    assert "还剩 1 个待完成" in answer
    assert "约 30 分钟" in answer
    assert "背单词（20 分钟，已完成）" in answer
    assert "听力练习（30 分钟，待完成）" in answer
    assert "跳过任务" not in answer
    assert suggestions == ["去打卡", "查看任务理由"]


def test_build_rule_answer_review_branch(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "复习间隔是多久")

    assert "1 / 2 / 4 / 7 / 15" in answer
    assert "答错会回到 1 天" in answer
    assert suggestions == ["查看掌握度", "生成计划"]


def test_build_rule_answer_mistakes_without_records(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "错题怎么分析")

    assert "近 7 天还没有错题记录" in answer
    assert suggestions == ["录入错题"]


def test_build_rule_answer_mistakes_groups_categories(db, db_user_goal):
    user, goal = db_user_goal
    db.add_all(
        [
            Mistake(user_id=user.id, goal_id=goal.id, question="q1", category_label="概念不清"),
            Mistake(user_id=user.id, goal_id=goal.id, question="q2", category_label="方法不会"),
            Mistake(user_id=user.id, goal_id=goal.id, question="q3", category_label="概念不清"),
        ]
    )
    db.commit()

    answer, suggestions = qa.build_rule_answer(db, user, goal, "为什么错这么多")

    assert "近 7 天共 3 道错题" in answer
    assert "概念不清 2 道" in answer
    assert "方法不会 1 道" in answer
    assert suggestions == ["查看错题本", "插入补救任务"]


def test_build_rule_answer_ignores_old_mistakes(db, db_user_goal):
    user, goal = db_user_goal
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            question="old",
            category_label="粗心",
            created_at=datetime.combine(date.today() - timedelta(days=30), datetime.min.time()),
        )
    )
    db.commit()

    answer, _ = qa.build_rule_answer(db, user, goal, "错题怎么分析")

    assert "近 7 天还没有错题记录" in answer


def test_build_rule_answer_plan_branch(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "来得及吗")

    assert "当前目标是「CET-4」" in answer
    assert "还剩 30 天" in answer
    assert "优先级公式" in answer
    assert suggestions == ["生成计划", "智能重排"]


def test_build_rule_answer_motivation_branch(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "我不想学了")

    assert "只做 10 分钟" in answer
    assert "从 3 个降到 2 个" in answer
    assert suggestions == ["查看学习节奏", "调整每日时长"]


def test_build_rule_answer_default_branch(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, "你好呀")

    assert "我可以帮你查今天学什么" in answer
    assert "今天有 0 个待完成任务" in answer
    assert suggestions == ["今天学什么", "我的薄弱点", "还剩几天"]


def test_build_rule_answer_handles_none_question(db, db_user_goal):
    user, goal = db_user_goal

    answer, suggestions = qa.build_rule_answer(db, user, goal, None)

    assert "我可以帮你查今天学什么" in answer
    assert suggestions == ["今天学什么", "我的薄弱点", "还剩几天"]


# --------------------------------------------------------------------------
# answer_question：规则兜底与 LLM 润色分支
# --------------------------------------------------------------------------


def test_answer_question_uses_rule_when_llm_unavailable(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    fake = _FakeLLM("不应被使用", available=False)
    monkeypatch.setattr(qa, "llm", fake)

    result = asyncio.run(qa.answer_question(db, user, goal, "你好呀"))

    assert result["source"] == "rule"
    assert "我可以帮你查今天学什么" in result["answer"]
    assert result["suggestions"] == ["今天学什么", "我的薄弱点", "还剩几天"]
    assert fake.calls == []


def test_answer_question_prefers_llm_text_and_strips_space(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    fake = _FakeLLM("  明天先背 20 个单词。  ", available=True)
    monkeypatch.setattr(qa, "llm", fake)

    result = asyncio.run(qa.answer_question(db, user, goal, "你好呀"))

    assert result["source"] == "llm"
    assert result["answer"] == "明天先背 20 个单词。"
    assert len(fake.calls) == 1
    system, prompt, temperature, max_tokens = fake.calls[0]
    assert "你是学迹学习教练" in system
    assert "80 字以内" in system
    assert "用户问题：你好呀" in prompt
    assert "可用事实：" in prompt
    assert temperature == 0.4
    assert max_tokens == 300


def test_answer_question_falls_back_when_llm_returns_empty(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    monkeypatch.setattr(qa, "llm", _FakeLLM(None, available=True))

    result = asyncio.run(qa.answer_question(db, user, goal, "你好呀"))

    assert result["source"] == "rule"
    assert "我可以帮你查今天学什么" in result["answer"]


def test_answer_question_skips_llm_without_goal(db, db_user_goal, monkeypatch):
    user, _ = db_user_goal
    fake = _FakeLLM("不应被使用", available=True)
    monkeypatch.setattr(qa, "llm", fake)

    result = asyncio.run(qa.answer_question(db, user, None, "今天学什么"))

    assert result["source"] == "rule"
    assert "你还没有设置考试目标" in result["answer"]
    assert fake.calls == []


# --------------------------------------------------------------------------
# /api/coach/ask 接口
# --------------------------------------------------------------------------


def test_coach_ask_without_goal(api, auth):
    response = api(
        "POST",
        "/api/coach/ask",
        token=auth["token"],
        json={"question": "今天学什么"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "rule"
    assert "你还没有设置考试目标" in body["answer"]
    assert body["suggestions"] == ["创建考试目标", "导入学习资料"]


def test_coach_ask_uses_latest_goal(api, auth, goal):
    response = api(
        "POST",
        "/api/coach/ask",
        token=auth["token"],
        json={"question": "还有几天"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "距离「大学英语四级」还有 40 天" in body["answer"]
    assert "每天可用 90 分钟" in body["answer"]
    assert body["source"] == "rule"


def test_coach_ask_falls_back_when_goal_belongs_to_another_user(api, auth, goal, db):
    other = User(username="other", password_hash="x", nickname="他人")
    db.add(other)
    db.flush()
    other_goal = Goal(
        user_id=other.id,
        exam_name="考研数学",
        exam_date=date.today() + timedelta(days=200),
        daily_minutes=60,
    )
    db.add(other_goal)
    db.commit()

    response = api(
        "POST",
        "/api/coach/ask",
        token=auth["token"],
        json={"question": "还有几天", "goal_id": other_goal.id},
    )

    assert response.status_code == 200, response.text
    assert "大学英语四级" in response.json()["answer"]
    assert "考研数学" not in response.json()["answer"]


def test_coach_ask_falls_back_when_goal_id_missing(api, auth, goal):
    response = api(
        "POST",
        "/api/coach/ask",
        token=auth["token"],
        json={"question": "还有几天", "goal_id": 999999},
    )

    assert response.status_code == 200, response.text
    assert "还有 40 天" in response.json()["answer"]


def test_coach_ask_rejects_empty_question(api, auth, goal):
    response = api(
        "POST",
        "/api/coach/ask",
        token=auth["token"],
        json={"question": ""},
    )

    assert response.status_code == 422