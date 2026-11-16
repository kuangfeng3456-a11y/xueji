from datetime import date, datetime, timedelta

from app.models import Mastery, MasteryHistory, Mistake, Report, Task
from app.services import reporting
from app.services.mastery_service import ensure_mastery
from app.services.reporting import build_weekly_report, generate_weekly_report
from app.services.rules import week_bounds
from tests.conftest import add_points


def _add_task(db, user, goal, day, status="pending", duration=30):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day,
        title="任务",
        type="study",
        duration_min=duration,
        status=status,
        reason="测试",
        priority=1.0,
        source="plan",
    )
    db.add(task)
    db.flush()
    return task


def test_weekly_report_computes_completion_and_delta(db, db_user_goal):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力", "阅读"))
    today = date.today()
    week_start, _ = week_bounds(today)

    _add_task(db, user, goal, week_start, "done", 40)
    _add_task(db, user, goal, week_start + timedelta(days=1), "done", 20)
    _add_task(db, user, goal, week_start + timedelta(days=2), "pending")
    _add_task(db, user, goal, week_start + timedelta(days=3), "skipped")

    ensure_mastery(db, user.id, points[0]).value = 0.6
    ensure_mastery(db, user.id, points[1]).value = 0.2
    db.add_all(
        [
            MasteryHistory(user_id=user.id, kp_id=points[0].id, day=week_start, value=0.2),
            MasteryHistory(user_id=user.id, kp_id=points[1].id, day=week_start, value=0.2),
        ]
    )
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=points[0].id,
            question="题",
            user_answer="答",
            correct_answer="对",
            category="method",
            category_label="方法不会",
            suggestion="复习",
            source="text",
            created_at=datetime.combine(week_start, datetime.min.time()) + timedelta(hours=8),
        )
    )
    db.commit()

    report = build_weekly_report(db, user, goal, week_start=week_start)

    assert report.week_start == week_start
    assert report.week_end == week_start + timedelta(days=6)
    assert report.completion_rate == 0.5
    assert report.mastery_delta == 0.2
    assert report.focus == "阅读"
    assert "完成 2/4 个任务" in report.content
    assert "完成率 50%" in report.content
    assert "方法不会 1 道" in report.content
    assert "累计学习 60 分钟" in report.content
    assert "下周优先补「阅读」" in report.content


def test_weekly_report_without_baseline_keeps_delta_zero(db, db_user_goal):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("听力",))
    ensure_mastery(db, user.id, points[0]).value = 0.4
    db.commit()

    report = build_weekly_report(db, user, goal, week_start=date.today())
    assert report.mastery_delta == 0.0
    assert "保持当前节奏" in report.content or "优先补" in report.content


def test_weekly_report_is_upserted_per_week(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal, names=("听力",))
    week_start, _ = week_bounds(date.today())

    first = build_weekly_report(db, user, goal, week_start=week_start)
    second = build_weekly_report(db, user, goal, week_start=week_start)

    assert first.id == second.id
    assert db.query(Report).count() == 1


def test_weekly_report_normalises_week_start(db, db_user_goal):
    user, goal = db_user_goal
    sunday = date.today() + timedelta(days=(6 - date.today().weekday()) % 7)
    report = build_weekly_report(db, user, goal, week_start=sunday)
    assert report.week_start.weekday() == 0


def test_weekly_report_empty_data(db, db_user_goal):
    user, goal = db_user_goal
    report = build_weekly_report(db, user, goal, week_start=date.today())
    assert report.completion_rate == 0.0
    assert report.mastery_delta == 0.0
    assert report.focus == "保持节奏"
    assert "暂无错题记录" in report.content
    assert "保持当前节奏" in report.content


class _FakeLLM:
    def __init__(self, reply, available=True):
        self.reply = reply
        self.available = available

    async def chat(self, system, user, temperature=0.2, max_tokens=900):
        return self.reply


def test_generate_weekly_report_without_llm(db, db_user_goal):
    import asyncio

    user, goal = db_user_goal
    report = asyncio.run(generate_weekly_report(db, user, goal, use_llm=False))
    assert "【本周概览】" in report.content
    assert "教练点评" not in report.content


def test_generate_weekly_report_appends_llm_comment(monkeypatch, db, db_user_goal):
    import asyncio

    user, goal = db_user_goal
    monkeypatch.setattr(reporting, "llm", _FakeLLM("  保持节奏，明天先做听力。  "))
    report = asyncio.run(generate_weekly_report(db, user, goal, use_llm=True))
    assert report.content.endswith("【教练点评】保持节奏，明天先做听力。")


def test_generate_weekly_report_ignores_empty_llm_reply(monkeypatch, db, db_user_goal):
    import asyncio

    user, goal = db_user_goal
    monkeypatch.setattr(reporting, "llm", _FakeLLM(None))
    report = asyncio.run(generate_weekly_report(db, user, goal, use_llm=True))
    assert "教练点评" not in report.content