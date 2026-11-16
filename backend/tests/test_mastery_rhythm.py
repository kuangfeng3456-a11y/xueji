from datetime import date, datetime, timedelta

import pytest

from app.models import Mastery, MasteryHistory, Task
from app.services import mastery_service, rhythm
from app.services.rhythm import build_rhythm, hour_to_period


def test_hour_to_period_boundaries():
    assert hour_to_period(0) == "night"
    assert hour_to_period(4) == "night"
    assert hour_to_period(5) == "morning"
    assert hour_to_period(11) == "morning"
    assert hour_to_period(12) == "afternoon"
    assert hour_to_period(17) == "afternoon"
    assert hour_to_period(18) == "evening"
    assert hour_to_period(22) == "evening"
    assert hour_to_period(23) == "night"


def _add_task(db, user, goal, day, status, duration=30, done_hour=20, kp_id=None):
    done_at = None
    if status == "done":
        done_at = datetime.combine(day, datetime.min.time()) + timedelta(hours=done_hour)
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=kp_id,
        day=day,
        title="测试任务",
        type="study",
        duration_min=duration,
        status=status,
        reason="测试",
        priority=1.0,
        source="plan",
        done_at=done_at,
    )
    db.add(task)
    db.flush()
    return task


def test_rhythm_without_history(db, db_user_goal):
    user, goal = db_user_goal
    result = build_rhythm(db, user.id, goal.id)
    assert result["sampled_tasks"] == 0
    assert result["completion_rate"] == 0.0
    assert result["habit"] == "节奏待建立"
    assert result["tasks_per_day"] == 3
    assert result["peak_period"] is None
    assert result["peak_period_label"] is None
    assert "3 天" in result["suggestion"]


def test_rhythm_detects_peak_period_and_low_completion(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    for offset in range(1, 7):
        day = today - timedelta(days=offset)
        status = "done" if offset <= 2 else "pending"
        _add_task(db, user, goal, day, status, done_hour=9)
    db.commit()

    result = build_rhythm(db, user.id, goal.id, today=today)
    assert result["sampled_tasks"] == 6
    assert result["completion_rate"] == pytest.approx(2 / 6, abs=1e-4)
    assert result["overdue_pending"] == 4
    assert result["peak_period"] == "morning"
    assert result["peak_period_label"] == "上午"
    assert result["on_time_rate"] == 1.0
    assert result["tasks_per_day"] == 2
    assert "下调为 2 个" in result["suggestion"]
    assert sum(item["count"] for item in result["periods"]) == 2


def test_rhythm_detects_procrastination(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    for offset in range(1, 5):
        task = _add_task(db, user, goal, today - timedelta(days=offset), "done", done_hour=21)
        task.done_at = task.done_at + timedelta(days=3)
    for offset in range(5, 9):
        _add_task(db, user, goal, today - timedelta(days=offset), "pending")
    db.commit()

    result = build_rhythm(db, user.id, goal.id, today=today)
    assert result["avg_delay_days"] >= 2
    assert result["on_time_rate"] == 0.0
    assert result["tasks_per_day"] == 2
    assert "拖延" in result["habit"] or "平均比计划晚" in result["suggestion"]


def test_rhythm_suggests_habit_slot_when_on_time(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    for offset in range(1, 5):
        _add_task(db, user, goal, today - timedelta(days=offset), "done", done_hour=19)
    db.commit()

    result = build_rhythm(db, user.id, goal.id, today=today)
    assert result["peak_period"] == "evening"
    assert result["tasks_per_day"] == 3
    assert result["completion_rate"] == 1.0
    assert result["habit"] == "晚上型 · 节奏稳定"
    assert "习惯在晚上" in result["suggestion"]


def test_rhythm_handles_two_late_tasks_and_skips(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    for offset in range(1, 3):
        task = _add_task(db, user, goal, today - timedelta(days=offset), "done", done_hour=10)
        task.done_at = task.done_at + timedelta(days=2)
    for offset in range(3, 5):
        _add_task(db, user, goal, today - timedelta(days=offset), "pending")
    for offset in range(5, 7):
        _add_task(db, user, goal, today - timedelta(days=offset), "skipped")
    db.commit()

    result = build_rhythm(db, user.id, goal.id, today=today)
    assert result["sampled_tasks"] == 6
    assert result["skip_rate"] == pytest.approx(2 / 6, abs=1e-4)
    assert result["tasks_per_day"] == 3
    assert "平均比计划晚" in result["suggestion"]


def test_rhythm_clamps_window(db, db_user_goal):
    user, goal = db_user_goal
    assert build_rhythm(db, user.id, goal.id, days=1)["window_days"] == rhythm.MIN_WINDOW_DAYS
    assert build_rhythm(db, user.id, goal.id, days=999)["window_days"] == rhythm.MAX_WINDOW_DAYS


def test_rhythm_ignores_done_task_without_done_at(db, db_user_goal):
    user, goal = db_user_goal
    task = _add_task(db, user, goal, date.today() - timedelta(days=1), "done")
    task.done_at = None
    db.commit()

    result = build_rhythm(db, user.id, goal.id)
    assert result["completion_rate"] == 1.0
    assert result["avg_delay_days"] == 0.0
    assert result["peak_period"] is None


def test_ensure_mastery_creates_once(db, db_user_goal):
    from tests.conftest import add_points

    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]

    record = mastery_service.ensure_mastery(db, user.id, point)
    assert record.value == 0.0
    again = mastery_service.ensure_mastery(db, user.id, point)
    assert again.id == record.id
    assert mastery_service.get_mastery(db, user.id, point.id).id == record.id
    assert mastery_service.get_mastery(db, user.id, 999999) is None


def test_ensure_goal_mastery_covers_all_points(db, db_user_goal):
    from tests.conftest import add_points

    user, goal = db_user_goal
    add_points(db, goal)
    mastery_service.ensure_goal_mastery(db, user.id, goal.id)
    rows = db.query(Mastery).filter(Mastery.user_id == user.id).all()
    assert len(rows) == 3
    # 幂等
    mastery_service.ensure_goal_mastery(db, user.id, goal.id)
    assert db.query(Mastery).filter(Mastery.user_id == user.id).count() == 3


def test_record_history_upserts_same_day(db, db_user_goal):
    from tests.conftest import add_points

    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    day = date.today()

    mastery_service.record_history(db, user.id, point.id, 0.2, day)
    db.flush()
    mastery_service.record_history(db, user.id, point.id, 0.55, day)
    db.flush()

    rows = db.query(MasteryHistory).all()
    assert len(rows) == 1
    assert rows[0].value == 0.55


def test_apply_answer_updates_mastery_and_schedule(db, db_user_goal):
    from tests.conftest import add_points

    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    today = date.today()

    record = mastery_service.apply_answer(db, user.id, point, True, day=today)
    assert record.value == 0.08
    assert record.review_stage == 1
    assert record.next_review_at == today + timedelta(days=2)

    record = mastery_service.apply_answer(db, user.id, point, False, day=today)
    assert record.value == 0.0957
    assert record.review_stage == 0
    assert record.next_review_at == today + timedelta(days=1)

    history = db.query(MasteryHistory).filter(MasteryHistory.kp_id == point.id).all()
    assert len(history) == 1
    assert history[0].value == 0.0957


def test_touch_history_for_today_is_idempotent(db, db_user_goal):
    from tests.conftest import add_points

    user, goal = db_user_goal
    add_points(db, goal)
    mastery_service.touch_history_for_today(db, user.id, goal.id)
    mastery_service.touch_history_for_today(db, user.id, goal.id)
    assert db.query(MasteryHistory).count() == 3