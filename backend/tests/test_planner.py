from collections import defaultdict
from datetime import date, datetime, timedelta

import pytest

from app.models import KnowledgePoint, Mastery, Mistake, ReplanLog, Task
from app.services.mastery_service import ensure_mastery
from app.services.planner import (
    REMEDIAL_MINUTES,
    TASKS_PER_DAY,
    build_plan,
    replan,
    task_to_dict,
)
from tests.conftest import add_points


def _add_task(db, user, goal, day, status="pending", duration=30, priority=1.0, kp_id=None, kind="study"):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=kp_id,
        day=day,
        title=f"{kind}：测试知识点",
        type=kind,
        duration_min=duration,
        status=status,
        reason="测试任务",
        priority=priority,
        source="plan",
        done_at=datetime.utcnow() if status == "done" else None,
    )
    db.add(task)
    db.flush()
    return task


def test_build_plan_creates_daily_micro_tasks(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal)
    today = date.today()

    result = build_plan(db, user.id, goal, days=7, today=today)

    assert result["days"] == 7
    assert len(result["tasks"]) == 7 * TASKS_PER_DAY
    assert result["total_minutes"] == 7 * goal.daily_minutes
    per_day = defaultdict(int)
    for task in result["tasks"]:
        per_day[task["day"]] += task["duration_min"]
    assert set(per_day) == {today + timedelta(days=offset) for offset in range(7)}
    assert all(minutes <= goal.daily_minutes for minutes in per_day.values())
    assert "微任务" in result["summary"]
    assert all(task["reason"] and task["priority"] > 0 for task in result["tasks"])
    assert all(task["kp_name"] for task in result["tasks"])


def test_build_plan_without_points_returns_empty_summary(db, db_user_goal):
    user, goal = db_user_goal
    result = build_plan(db, user.id, goal, today=date.today())
    assert result["tasks"] == []
    assert result["days"] == 0
    assert result["total_minutes"] == 0
    assert "知识点" in result["summary"]


def test_build_plan_horizon_limited_by_exam_date(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal)
    goal.exam_date = date.today() + timedelta(days=3)
    db.commit()

    result = build_plan(db, user.id, goal, days=7)
    assert result["days"] == 3
    assert len(result["tasks"]) == 3 * TASKS_PER_DAY


def test_build_plan_only_schedules_leaf_points(db, db_user_goal):
    user, goal = db_user_goal
    parent = KnowledgePoint(goal_id=goal.id, name="听力", weight=2.0)
    db.add(parent)
    db.flush()
    child_a = KnowledgePoint(goal_id=goal.id, name="短对话", parent_id=parent.id, weight=1.5)
    child_b = KnowledgePoint(goal_id=goal.id, name="长对话", parent_id=parent.id, weight=1.2)
    db.add_all([child_a, child_b])
    db.commit()

    result = build_plan(db, user.id, goal, days=2, today=date.today())
    assert {task["kp_id"] for task in result["tasks"]} == {child_a.id, child_b.id}


def test_build_plan_schedules_due_review_first(db, db_user_goal):
    user, goal = db_user_goal
    points = add_points(db, goal)
    today = date.today()
    record = ensure_mastery(db, user.id, points[-1])
    record.value = 0.5
    record.next_review_at = today
    db.commit()

    result = build_plan(db, user.id, goal, days=1, today=today)
    first = result["tasks"][0]
    assert first["type"] == "review"
    assert first["kp_id"] == points[-1].id
    assert "遗忘曲线" in first["reason"]
    assert first["duration_min"] >= 10


def test_build_plan_regenerate_replaces_pending_plan_tasks(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal)
    today = date.today()
    build_plan(db, user.id, goal, days=7, today=today)
    db.commit()
    assert db.query(Task).count() == 21

    build_plan(db, user.id, goal, days=7, regenerate=True, today=today)
    db.commit()
    assert db.query(Task).count() == 21


def test_build_plan_adapts_task_count_to_completion_rate(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal)
    today = date.today()
    for offset in range(1, 7):
        _add_task(
            db,
            user,
            goal,
            today - timedelta(days=offset),
            status="done" if offset <= 2 else "pending",
        )
    db.commit()

    result = build_plan(db, user.id, goal, days=7, today=today)
    assert len(result["tasks"]) == 7 * 2
    assert "调整为 2 个" in result["summary"]


def test_task_to_dict_keeps_knowledge_point_name(db, db_user_goal):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    task = _add_task(db, user, goal, date.today(), kp_id=point.id)
    payload = task_to_dict(task, {point.id: point})
    assert payload["kp_name"] == "听力"
    assert payload["id"] == task.id
    assert payload["source"] == "plan"
    assert task_to_dict(task, {})["kp_name"] is None


def test_replan_shifts_overdue_tasks_to_today(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    overdue = _add_task(db, user, goal, today - timedelta(days=2))
    db.commit()

    result = replan(db, user.id, goal, today=today)

    db.refresh(overdue)
    assert overdue.day == today
    assert "自动顺延" in overdue.reason
    assert any(change["kind"] == "shift" for change in result["changes"])


def test_replan_inserts_remedial_task_after_repeated_mistakes(db, db_user_goal):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    today = date.today()
    for _ in range(2):
        db.add(
            Mistake(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=point.id,
                question="题目",
                user_answer="答案",
                correct_answer="正确答案",
                category="method",
                category_label="方法不会",
                suggestion="复习步骤",
                source="text",
                created_at=datetime.utcnow(),
            )
        )
    db.commit()

    result = replan(db, user.id, goal, today=today)
    kinds = [change["kind"] for change in result["changes"]]
    assert "insert_remedial" in kinds
    remedial = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.type == "remedial")
        .all()
    )
    assert len(remedial) == 1
    assert remedial[0].duration_min == REMEDIAL_MINUTES
    assert "7 天" in remedial[0].reason

    # 已有补救任务时不重复插入
    second = replan(db, user.id, goal, today=today)
    assert "insert_remedial" not in [change["kind"] for change in second["changes"]]
    assert db.query(Task).filter(Task.type == "remedial").count() == 1


def test_replan_adds_exam_sprint_review(db, db_user_goal):
    user, goal = db_user_goal
    point = add_points(db, goal, names=("听力",))[0]
    today = date.today()
    goal.exam_date = today + timedelta(days=1)
    db.commit()
    _add_task(db, user, goal, today, duration=30, kp_id=point.id, kind="study")
    db.commit()

    result = replan(db, user.id, goal, today=today)
    assert any(change["kind"] == "exam_sprint" for change in result["changes"])
    review = db.query(Task).filter(Task.user_id == user.id, Task.type == "review").all()
    assert len(review) == 1
    assert review[0].duration_min == 15
    assert "距考试不足 7 天" in review[0].reason


def test_replan_defers_tasks_exceeding_daily_budget(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    for priority in (3.0, 2.0, 1.0):
        _add_task(db, user, goal, today, duration=40, priority=priority)
    db.commit()

    result = replan(db, user.id, goal, today=today)
    deferred = [change for change in result["changes"] if change["kind"] == "defer"]
    assert len(deferred) == 1
    moved = db.query(Task).filter(Task.user_id == user.id, Task.day == today + timedelta(days=1)).all()
    assert len(moved) == 1
    assert "推迟到" in moved[0].reason


def test_replan_drops_tasks_when_exam_is_tomorrow(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today + timedelta(days=1)
    db.commit()
    for priority in (3.0, 2.0, 1.0):
        _add_task(db, user, goal, today, duration=40, priority=priority)
    db.commit()

    result = replan(db, user.id, goal, today=today)
    dropped = [change for change in result["changes"] if change["kind"] == "drop"]
    assert len(dropped) == 1
    assert db.query(Task).filter(Task.status == "skipped").count() == 1


def test_replan_keeps_plan_when_nothing_changes(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()

    result = replan(db, user.id, goal, trigger="manual", today=today)

    assert [change["kind"] for change in result["changes"]] == ["keep"]
    assert result["trigger"] == "manual"
    log = db.query(ReplanLog).one()
    assert log.trigger == "manual"
    assert "keep" in log.changes


def test_replan_returns_today_tasks_excluding_skipped(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _add_task(db, user, goal, today, status="pending")
    _add_task(db, user, goal, today, status="skipped")
    db.commit()

    result = replan(db, user.id, goal, today=today)
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["source"] == "plan"


def test_build_plan_is_deterministic_for_same_inputs(db, db_user_goal):
    user, goal = db_user_goal
    add_points(db, goal)
    today = date.today()

    first = build_plan(db, user.id, goal, days=2, today=today)
    db.rollback()
    second = build_plan(db, user.id, goal, days=2, today=today)

    assert [task["title"] for task in first["tasks"]] == [task["title"] for task in second["tasks"]]


def test_plan_respects_mastery_when_ranking(db, db_user_goal):
    user, goal = db_user_goal
    points = add_points(db, goal, names=("薄弱点", "已掌握点"))
    weak, strong = points
    ensure_mastery(db, user.id, weak).value = 0.05
    ensure_mastery(db, user.id, strong).value = 0.95
    db.commit()

    result = build_plan(db, user.id, goal, days=1, today=date.today())
    assert result["tasks"][0]["kp_id"] == weak.id
    assert result["tasks"][0]["priority"] > result["tasks"][1]["priority"]