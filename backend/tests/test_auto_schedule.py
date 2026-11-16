"""按剩余时间自动调整计划的服务层测试（app/services/auto_schedule.py）。

覆盖：今日无任务自动生成、逾期顺延重排、临考冲刺复习、无需调整、
强制模式剩余任务计数，以及 build_plan / replan 的调用参数与触发器。
"""

from datetime import date, timedelta

from app.models import KnowledgePoint, Task
from app.services import auto_schedule as auto_schedule_module
from app.services.auto_schedule import auto_adjust_today


def _add_points(db, goal, names=("听力", "阅读", "写作")):
    created = []
    for index, name in enumerate(names):
        point = KnowledgePoint(goal_id=goal.id, name=name, weight=1.0 + index * 0.5)
        db.add(point)
        db.flush()
        created.append(point)
    db.commit()
    return created


def _add_task(db, user, goal, day, *, status="pending", type_="study", title="听力练习", duration=20):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day,
        title=title,
        type=type_,
        duration_min=duration,
        status=status,
        priority=1.0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_auto_adjust_builds_today_plan_when_empty(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal, ("听力",))

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is True
    assert result["summary"] == "今天还没有任务，已根据剩余时间自动生成今日计划。"
    assert result["changes"][0]["kind"] == "auto_plan"
    assert result["days_left"] == 30
    assert result["force_mode"] is False
    assert result["sprint_mode"] is False
    assert result["mandatory_remaining"] >= 1

    today_tasks = db.query(Task).filter(Task.day == date.today()).all()
    assert len(today_tasks) == result["mandatory_remaining"]
    assert all(task.status == "pending" for task in today_tasks)


def test_auto_adjust_does_nothing_without_knowledge_points(db, db_user_goal):
    user, goal = db_user_goal

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is False
    assert result["summary"] == ""
    assert result["changes"] == []
    assert result["mandatory_remaining"] == 0
    assert db.query(Task).count() == 0


def test_auto_adjust_shifts_overdue_tasks_when_today_empty(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal, ("阅读",))
    overdue = _add_task(db, user, goal, date.today() - timedelta(days=2), title="阅读真题")

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is True
    assert "检测到 1 个逾期任务" in result["summary"]
    assert "已自动顺延并重排今天的学习安排。" in result["summary"]
    assert any(change["kind"] == "shift" for change in result["changes"])

    db.refresh(overdue)
    assert overdue.day == date.today()
    assert "因未完成已自动顺延" in overdue.reason


def test_auto_adjust_replans_overdue_even_when_today_has_tasks(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal, ("阅读",))
    _add_task(db, user, goal, date.today(), title="今日任务")
    _add_task(db, user, goal, date.today() - timedelta(days=1), title="昨日未完成")

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is True
    assert result["summary"] == "检测到 1 个逾期任务，已自动重排并优先补上。"
    assert any(change["kind"] == "shift" for change in result["changes"])


def test_auto_adjust_enters_sprint_mode_near_exam(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)
    _add_task(db, user, goal, date.today(), title="冲刺练习")
    goal.exam_date = date.today() + timedelta(days=3)
    db.commit()

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is True
    assert result["sprint_mode"] is True
    assert "距考试只剩 3 天" in result["summary"]
    assert any(change["kind"] == "exam_sprint" for change in result["changes"])
    assert db.query(Task).filter(Task.type == "review").count() == 1


def test_auto_adjust_skips_sprint_when_review_already_present(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)
    _add_task(db, user, goal, date.today(), title="复习：听力", type_="review")
    goal.exam_date = date.today() + timedelta(days=2)
    db.commit()

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is False
    assert result["summary"] == ""
    assert result["sprint_mode"] is True
    assert result["changes"] == []


def test_auto_adjust_leaves_regular_day_untouched(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)
    _add_task(db, user, goal, date.today(), title="常规学习")

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is False
    assert result["summary"] == ""
    assert result["sprint_mode"] is False
    assert result["days_left"] == 30


def test_auto_adjust_counts_mandatory_pending_in_force_mode(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)
    _add_task(db, user, goal, date.today(), title="任务一")
    _add_task(db, user, goal, date.today(), title="任务二", status="done")
    _add_task(db, user, goal, date.today(), title="任务三", status="skipped")
    goal.force_mode = True
    db.commit()

    result = auto_adjust_today(db, user, goal)

    assert result["force_mode"] is True
    assert result["mandatory_remaining"] == 1
    assert result["adjusted"] is False


def test_skipped_task_blocks_new_plan_for_the_day(db, db_user_goal):
    """锁定当前实现：skipped 任务仍被视为“当天已排计划”，不会再生成新任务。

    该行为会使用户跳过任务后当天无计划可执行，属已识别的覆盖缺口，
    建议 build_plan 的 existing_days 查询排除 skipped 任务。
    """
    user, goal = db_user_goal
    _add_points(db, goal, ("听力",))
    _add_task(db, user, goal, date.today(), title="已跳过", status="skipped")

    result = auto_adjust_today(db, user, goal)

    assert result["adjusted"] is False
    assert result["summary"] == ""
    assert result["mandatory_remaining"] == 0
    assert db.query(Task).filter(Task.status == "pending").count() == 0


def test_auto_adjust_passes_expected_arguments_to_build_plan(monkeypatch, db, db_user_goal):
    user, goal = db_user_goal
    fixed_day = date(2026, 3, 2)
    captured = {}

    def fake_build_plan(db_, user_id, goal_, days=7, regenerate=False, today=None):
        captured.update(
            {
                "db": db_,
                "user_id": user_id,
                "goal_id": goal_.id,
                "days": days,
                "regenerate": regenerate,
                "today": today,
            }
        )
        return {"tasks": [{"id": 1}], "summary": "生成 1 个任务", "days": 1, "total_minutes": 20}

    monkeypatch.setattr(auto_schedule_module, "build_plan", fake_build_plan)

    result = auto_adjust_today(db, user, goal, today=fixed_day)

    assert captured["db"] is db
    assert captured["user_id"] == user.id
    assert captured["goal_id"] == goal.id
    assert captured["days"] == 1
    assert captured["regenerate"] is False
    assert captured["today"] == fixed_day
    assert result["adjusted"] is True
    assert result["changes"] == [
        {"kind": "auto_plan", "detail": "生成 1 个任务", "task_id": None}
    ]


def test_auto_adjust_calls_replan_with_overdue_trigger(monkeypatch, db, db_user_goal):
    user, goal = db_user_goal
    fixed_day = date(2026, 3, 2)
    _add_task(db, user, goal, fixed_day - timedelta(days=2), title="逾期任务")
    captured = {}

    def fake_replan(db_, user_id, goal_, trigger="manual", today=None):
        captured.update({"user_id": user_id, "trigger": trigger, "today": today})
        return {"trigger": trigger, "changes": [{"kind": "shift", "detail": "顺延"}], "tasks": []}

    monkeypatch.setattr(auto_schedule_module, "replan", fake_replan)

    result = auto_adjust_today(db, user, goal, today=fixed_day)

    assert captured["user_id"] == user.id
    assert captured["trigger"] == "auto_overdue"
    assert captured["today"] == fixed_day
    assert result["adjusted"] is True
    assert result["changes"] == [{"kind": "shift", "detail": "顺延"}]


def test_auto_adjust_calls_replan_with_sprint_trigger(monkeypatch, db, db_user_goal):
    user, goal = db_user_goal
    fixed_day = date(2026, 3, 2)
    _add_points(db, goal)
    _add_task(db, user, goal, fixed_day, title="临近考试")
    goal.exam_date = fixed_day + timedelta(days=2)
    db.commit()
    captured = {}

    def fake_replan(db_, user_id, goal_, trigger="manual", today=None):
        captured.update({"trigger": trigger, "today": today})
        return {"trigger": trigger, "changes": [{"kind": "exam_sprint"}], "tasks": []}

    monkeypatch.setattr(auto_schedule_module, "replan", fake_replan)

    result = auto_adjust_today(db, user, goal, today=fixed_day)

    assert captured["trigger"] == "auto_sprint"
    assert captured["today"] == fixed_day
    assert result["sprint_mode"] is True
    assert result["adjusted"] is True
    assert result["summary"] == "距考试只剩 2 天，已自动提高复习密度并插入冲刺复习。"