"""准备度、风险识别与风险救援（readiness）单元测试。"""

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Goal, KnowledgeGap, KnowledgePoint, Mastery, ReplanLog, Task, Violation
from app.services.readiness import (
    _rest_today,
    build_risks,
    compute_readiness,
    resolve_risk,
)


def _point(db, goal, name, weight=1.0):
    point = KnowledgePoint(goal_id=goal.id, name=name, weight=weight)
    db.add(point)
    db.flush()
    return point


def _mastery(db, user, point, value, next_review_at=None):
    db.add(
        Mastery(
            user_id=user.id,
            kp_id=point.id,
            value=value,
            next_review_at=next_review_at,
        )
    )
    db.flush()


def _task(db, user, goal, day, status="pending", minutes=30, priority=1.0, title="测试任务"):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day,
        title=title,
        type="study",
        duration_min=minutes,
        status=status,
        reason="测试",
        priority=priority,
        source="plan",
    )
    db.add(task)
    db.flush()
    return task


def _gap(db, user, goal, point, status="verified"):
    gap = KnowledgeGap(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=point.id,
        status=status,
        evidence="验证题答错",
        source="quiz",
    )
    db.add(gap)
    db.flush()
    return gap


# --------------------------------------------------------------------------
# compute_readiness
# --------------------------------------------------------------------------


def test_compute_readiness_without_points_is_critical(db, db_user_goal):
    user, goal = db_user_goal

    readiness = compute_readiness(db, user, goal)

    assert readiness["score"] == 0
    assert readiness["level"] == "critical"
    assert readiness["coverage"] == 0.0
    assert readiness["gap_count"] == 0
    assert readiness["factors"][0] == "高权重覆盖度 0%"
    assert readiness["factors"][1].startswith("时间匹配度 100%")


def test_compute_readiness_uses_weighted_coverage(db, db_user_goal):
    user, goal = db_user_goal
    heavy = _point(db, goal, "网络基础", weight=2.0)
    light = _point(db, goal, "写作", weight=1.0)
    _mastery(db, user, heavy, 0.5)
    _mastery(db, user, light, 1.0)
    db.commit()

    readiness = compute_readiness(db, user, goal)

    # (2.0 * 0.5 + 1.0 * 1.0) / 3.0 = 0.6667
    assert readiness["coverage"] == 0.6667
    assert readiness["score"] == 67
    assert readiness["level"] == "good"
    assert readiness["load_ratio"] == 0.0


def test_compute_readiness_subtracts_all_risk_penalties(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today + timedelta(days=10)
    goal.daily_minutes = 90
    point = _point(db, goal, "核心协议", weight=1.0)
    _mastery(db, user, point, 0.8)
    _gap(db, user, goal, point)
    _gap(db, user, goal, point)
    for _ in range(3):
        _task(db, user, goal, today - timedelta(days=1), "pending", 20)
    for offset in (1, 3):
        db.add(
            Violation(
                user_id=user.id,
                goal_id=goal.id,
                day=today - timedelta(days=offset),
                kind="abort",
                detail="退出专注",
            )
        )
    # 10 天 × 90 分钟 = 900 分钟可用；1800 分钟待完成 → 负荷 2.0
    for _ in range(2):
        _task(db, user, goal, today, "pending", 900)
    db.commit()

    readiness = compute_readiness(db, user, goal)

    # Ready = 100 × 0.8 × (0.7 + 0.3×0.5) − min(15, 3×2 + 3 + 2×2) = 68 − 13 = 55
    assert readiness["coverage"] == 0.8
    assert readiness["load_ratio"] == 2.0
    assert readiness["time_fit"] == 0.5
    assert readiness["penalty"] == 13
    assert readiness["gap_count"] == 2
    assert readiness["score"] == 55
    assert readiness["level"] == "risk"
    assert "已验证漏洞 2 个" in readiness["factors"]
    assert "逾期任务 3 个" in readiness["factors"]
    assert "近 7 天违约 2 次" in readiness["factors"]


def test_compute_readiness_level_boundaries(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "综合", weight=1.0)
    row = Mastery(user_id=user.id, kp_id=point.id, value=0.0)
    db.add(row)
    db.commit()

    expectations = ((0.81, "excellent"), (0.65, "good"), (0.45, "risk"), (0.2, "critical"))
    for value, level in expectations:
        row.value = value
        db.commit()
        readiness = compute_readiness(db, user, goal)
        assert readiness["score"] == round(value * 100)
        assert readiness["level"] == level


# --------------------------------------------------------------------------
# build_risks
# --------------------------------------------------------------------------


def test_build_risks_reports_high_knowledge_and_time_risk(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today + timedelta(days=10)
    goal.daily_minutes = 90
    first = _point(db, goal, "子网划分", weight=1.6)
    second = _point(db, goal, "路由协议", weight=1.6)
    _mastery(db, user, first, 0.2)
    _mastery(db, user, second, 0.25)
    _gap(db, user, goal, first)
    _gap(db, user, goal, second)
    _task(db, user, goal, today, "pending", 1300)
    db.commit()

    risks = build_risks(db, user, goal)
    by_code = {risk["code"]: risk for risk in risks}

    assert set(by_code) == {"knowledge", "time"}
    assert by_code["knowledge"]["level"] == "high"
    assert "已验证漏洞 2 个" in by_code["knowledge"]["reason"]
    assert by_code["knowledge"]["action"] == "生成修复任务"
    assert by_code["time"]["level"] == "high"
    # 1300 / 900 = 144%
    assert "144%" in by_code["time"]["reason"]
    assert by_code["time"]["action"] == "一键压缩与重排"


def test_build_risks_reports_medium_signals_and_strategy_gap(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.daily_minutes = 90
    weak = _point(db, goal, "薄弱高权重", weight=1.6)
    _mastery(db, user, weak, 0.2)
    verified = _point(db, goal, "已验证漏洞", weight=1.0)
    _mastery(db, user, verified, 0.9)
    _gap(db, user, goal, verified)
    # 30 天 × 90 = 2700 可用，3000 待完成 → 111%
    _task(db, user, goal, today, "pending", 3000)
    for _ in range(2):
        _task(db, user, goal, today - timedelta(days=1), "pending", 15)
    for index in range(5):
        point = _point(db, goal, "复习点%d" % index, weight=1.0)
        _mastery(db, user, point, 0.9, next_review_at=today)
    db.commit()

    risks = build_risks(db, user, goal)
    by_code = {risk["code"]: risk for risk in risks}

    assert by_code["knowledge"]["level"] == "medium"
    assert by_code["time"]["level"] == "medium"
    assert by_code["execution"]["level"] == "medium"
    assert by_code["memory"]["level"] == "medium"
    assert "策略风险" not in by_code.values()


def test_build_risks_silent_when_data_is_healthy(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "已掌握", weight=1.0)
    _mastery(db, user, point, 0.9)
    # 有错题记录时不会触发“策略未知”风险
    db.add(
        __import__("app.models", fromlist=["Mistake"]).Mistake(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            question="题目",
            user_answer="答案",
            correct_answer="正确",
        )
    )
    db.commit()

    assert build_risks(db, user, goal) == []


# --------------------------------------------------------------------------
# _rest_today
# --------------------------------------------------------------------------


def test_rest_today_keeps_single_task(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _task(db, user, goal, today)
    db.commit()

    moved, changes = _rest_today(db, user, goal, today)

    assert moved == 0
    assert changes == [{"kind": "keep", "detail": "今日任务已足够精简", "task_id": None}]


def test_rest_today_defers_lower_priority_tasks(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    kept = _task(db, user, goal, today, priority=5.0, title="高优先级")
    deferred = _task(db, user, goal, today, priority=1.0, title="低优先级")
    db.commit()

    moved, changes = _rest_today(db, user, goal, today)

    assert moved == 1
    assert kept.day == today
    assert deferred.day == today + timedelta(days=1)
    assert "风险救援" in deferred.reason
    assert changes[0]["kind"] == "defer"
    log = db.scalars(select(ReplanLog)).all()[-1]
    assert log.trigger == "risk_rest"
    assert json.loads(log.changes)[0]["kind"] == "defer"


def test_rest_today_skips_tasks_after_exam_deadline(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today
    _task(db, user, goal, today, priority=5.0)
    deferred = _task(db, user, goal, today, priority=1.0)
    db.commit()

    moved, changes = _rest_today(db, user, goal, today)

    assert moved == 0
    assert deferred.status == "skipped"
    assert any(item["kind"] == "defer" for item in changes)


# --------------------------------------------------------------------------
# resolve_risk
# --------------------------------------------------------------------------


def test_resolve_time_risk_defers_tasks_and_reports_change(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _task(db, user, goal, today, priority=5.0)
    _task(db, user, goal, today, priority=1.0)
    db.commit()

    result = resolve_risk(db, user, goal, "time", today=today)

    assert result["code"] == "time"
    assert "已降载" in result["message"]
    assert result["changes"][0]["kind"] == "defer"
    assert isinstance(result["before"], dict) and isinstance(result["after"], dict)
    deferred = db.scalars(
        select(Task).where(Task.goal_id == goal.id, Task.status == "pending")
    ).all()
    assert any(task.day == today + timedelta(days=1) for task in deferred)


def test_resolve_knowledge_risk_generates_repair_tasks(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "最薄弱", weight=1.0)
    second = _point(db, goal, "次薄弱", weight=1.0)
    strong = _point(db, goal, "已掌握", weight=1.0)
    _mastery(db, user, first, 0.1)
    _mastery(db, user, second, 0.3)
    _mastery(db, user, strong, 0.9)
    db.commit()

    result = resolve_risk(db, user, goal, "knowledge")

    assert result["message"] == "已生成 2 个漏洞修复任务，完成后请做验证题确认。"
    assert len(result["changes"]) == 2
    assert all(item["kind"] == "repair" for item in result["changes"])
    tasks = db.scalars(select(Task).where(Task.type == "remedial")).all()
    assert {task.kp_id for task in tasks} == {first.id, second.id}
    log = db.scalars(select(ReplanLog)).all()[-1]
    assert log.trigger == "risk_knowledge"


def test_resolve_memory_risk_inserts_review_task(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "到期知识点", weight=1.0)
    _mastery(db, user, point, 0.2, next_review_at=date.today())
    db.commit()

    result = resolve_risk(db, user, goal, "memory")

    assert result["message"] == "已插入 15 分钟复习任务。"
    assert result["changes"] == [
        {"kind": "review", "detail": "复习 到期知识点", "task_id": None}
    ]
    task = db.scalars(select(Task).where(Task.type == "review")).one()
    assert task.duration_min == 15
    assert task.kp_id == point.id


def test_resolve_unknown_risk_falls_back_to_strategy_advice(db, db_user_goal):
    user, goal = db_user_goal

    result = resolve_risk(db, user, goal, "strategy")

    assert "策略实验" in result["message"]
    assert result["changes"][0]["kind"] == "strategy"
    assert result["before"]["level"] == "critical"