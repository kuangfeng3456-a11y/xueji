"""考试未来模拟器（simulation）单元测试。"""

from datetime import date, timedelta

import pytest

from app.models import KnowledgePoint, Mastery, Task
from app.services.simulation import _leaves, _simulate, build_simulation


def _point(db, goal, name, parent_id=None, weight=1.0):
    point = KnowledgePoint(goal_id=goal.id, name=name, parent_id=parent_id, weight=weight)
    db.add(point)
    db.flush()
    return point


def _mastery(db, user, point, value):
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=value))
    db.flush()


def _pending_task(db, user, goal, minutes, day=None):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day or date.today(),
        title="待完成任务",
        type="study",
        duration_min=minutes,
        status="pending",
        reason="测试",
        priority=1.0,
        source="plan",
    )
    db.add(task)
    db.flush()
    return task


# --------------------------------------------------------------------------
# _leaves
# --------------------------------------------------------------------------


def test_leaves_returns_only_leaf_points(db, db_user_goal):
    user, goal = db_user_goal
    root = _point(db, goal, "听力")
    first = _point(db, goal, "短对话", root.id)
    second = _point(db, goal, "长对话", root.id)
    db.commit()

    leaves = _leaves(db, goal.id)

    assert {point.id for point in leaves} == {first.id, second.id}


def test_leaves_falls_back_when_parents_form_cycle(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "A")
    second = _point(db, goal, "B")
    first.parent_id = second.id
    second.parent_id = first.id
    db.commit()

    leaves = _leaves(db, goal.id)

    assert {point.id for point in leaves} == {first.id, second.id}


# --------------------------------------------------------------------------
# _simulate
# --------------------------------------------------------------------------


def test_simulate_returns_zero_without_points():
    assert _simulate([], [], daily_minutes=60, days=10, repair_first=False) == 0.0


def test_simulate_repair_first_prioritises_weak_points(db, db_user_goal):
    # 20 分钟只能覆盖 1 个知识点；权重差异用于区分两种排序策略
    values = [0.8, 0.3]
    weights = [10.0, 1.0]

    repaired = _simulate(values, weights, 20, 1, True)
    normal = _simulate(values, weights, 20, 1, False)

    # 修复优先按 (1-掌握度)^2*权重 选择，选中低掌握度节点
    assert repaired == pytest.approx(0.5893, abs=1e-4)
    # 普通推进按 (1-掌握度)*权重 选择，选中高权重节点
    assert normal == pytest.approx(0.5595, abs=1e-4)
    assert repaired > normal


def test_simulate_never_exceeds_one(db, db_user_goal):
    result = _simulate([0.99], [1.0], daily_minutes=600, days=200, repair_first=False)

    # 每天遗忘 + 单次增益会收敛到 0.96 左右，但永远不会超过 1
    assert 0.9 < result <= 1.0


# --------------------------------------------------------------------------
# build_simulation
# --------------------------------------------------------------------------


def test_build_simulation_without_points_returns_hint(db, db_user_goal):
    user, goal = db_user_goal

    result = build_simulation(db, user, goal)

    assert result["current_mastery"] == 0.0
    assert result["days_left"] == 30
    assert result["target_mastery"] == 0.7
    assert result["plans"] == []
    assert result["recommendation"] == "先导入知识点再模拟。"
    assert "还没有知识点" in result["uncertainty"]


def test_build_simulation_builds_four_comparable_plans(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "子网划分", weight=1.5)
    second = _point(db, goal, "路由协议", weight=1.0)
    _mastery(db, user, first, 0.4)
    _mastery(db, user, second, 0.6)
    db.commit()

    result = build_simulation(db, user, goal)

    plans = result["plans"]
    assert [plan["key"] for plan in plans] == ["keep", "more_time", "repair", "combo"]
    assert [plan["daily_minutes"] for plan in plans] == [90, 120, 90, 120]
    assert result["current_mastery"] == 0.5
    assert result["target_mastery"] == 0.7
    for plan in plans:
        assert plan["low"] <= plan["projected_mastery"] <= plan["high"]
        assert 0.0 <= plan["low"] <= 1.0
        assert 0.0 <= plan["high"] <= 1.0
        assert plan["load_ratio"] == 0.0
        assert plan["risk_level"] == "low"
    # 修复类方案多一条关键假设
    assert len(plans[0]["assumptions"]) == 3
    assert len(plans[2]["assumptions"]) == 4
    assert "不构成成绩保证" in result["uncertainty"]
    assert result["recommendation"].startswith("推荐「")
    assert "预计考试日平均掌握度" in result["recommendation"]


def test_build_simulation_marks_high_risk_when_time_is_short(db, db_user_goal):
    user, goal = db_user_goal
    goal.exam_date = date.today() + timedelta(days=1)
    point = _point(db, goal, "核心协议", weight=1.0)
    _mastery(db, user, point, 0.0)
    _pending_task(db, user, goal, 400)
    db.commit()

    result = build_simulation(db, user, goal)

    assert result["days_left"] == 1
    assert all(plan["risk_level"] == "high" for plan in result["plans"])
    # 400 / (1 * 90) = 4.4444
    assert result["plans"][0]["load_ratio"] == 4.4444
    # 所有方案负荷都超过 1.25，只能推荐预计掌握度最高的方案
    assert result["recommendation"].startswith("推荐「")


def test_build_simulation_marks_medium_risk_and_uses_interval(db, db_user_goal):
    user, goal = db_user_goal
    goal.exam_date = date.today() + timedelta(days=5)
    point = _point(db, goal, "综合", weight=1.0)
    _mastery(db, user, point, 0.5)
    db.commit()

    result = build_simulation(db, user, goal)

    assert result["target_mastery"] == 0.7
    for plan in result["plans"]:
        assert plan["risk_level"] == "medium"
        assert plan["projected_mastery"] == pytest.approx(0.7256, abs=1e-4)
        assert plan["low"] == pytest.approx(0.6856, abs=1e-4)
        assert plan["high"] == pytest.approx(0.7656, abs=1e-4)


def test_build_simulation_marks_low_risk_for_strong_mastery(db, db_user_goal):
    user, goal = db_user_goal
    goal.daily_minutes = 600
    point = _point(db, goal, "冲刺点", weight=1.0)
    _mastery(db, user, point, 0.3)
    db.commit()

    result = build_simulation(db, user, goal)

    # 30 天后掌握度可提升到 96% 左右，明显高于目标 70%
    assert all(plan["risk_level"] == "low" for plan in result["plans"])
    assert result["target_mastery"] == 0.7
    assert all(plan["projected_mastery"] >= 0.9 for plan in result["plans"])


def test_build_simulation_prefers_feasible_plan_over_best_raw_score(db, db_user_goal):
    user, goal = db_user_goal
    goal.exam_date = date.today() + timedelta(days=2)
    point = _point(db, goal, "核心", weight=1.0)
    _mastery(db, user, point, 0.0)
    # 250 / (2*90)=1.39 超过 1.25，而 250/(2*120)=1.04 可行
    _pending_task(db, user, goal, 250)
    db.commit()

    result = build_simulation(db, user, goal)

    feasible = [plan for plan in result["plans"] if plan["load_ratio"] <= 1.25]
    assert feasible
    recommended_projected = max(plan["projected_mastery"] for plan in feasible)
    assert ("%.0f%%" % (recommended_projected * 100)) in result["recommendation"]
    assert result["plans"][0]["load_ratio"] > 1.25