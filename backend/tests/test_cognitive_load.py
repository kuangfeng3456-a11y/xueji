"""认知负荷调节服务单元测试。

覆盖负荷分计算的四档阈值、推荐任务与时长、真实依赖集成路径，
以及 auto/reduce/increase/keep 四种调节动作与证据链写入。
疲劳指数与准备度在分支测试中被精确替换，避免依赖复杂历史数据。
"""

import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Evidence, Mastery, Mistake, Task
from app.services import cognitive_load as cognitive_load_module
from app.services.cognitive_load import apply_load, compute_load


def _readiness(score=70, coverage=0.5, load_ratio=0.5):
    return {"score": score, "coverage": coverage, "load_ratio": load_ratio}


def _patch_state(monkeypatch, fatigue=0, readiness=None):
    state = readiness or _readiness()
    monkeypatch.setattr(
        cognitive_load_module,
        "compute_readiness",
        lambda db, user, goal, today=None: dict(state),
    )
    monkeypatch.setattr(
        cognitive_load_module,
        "build_fatigue",
        lambda db, user_id, goal_id, today=None: {"score": fatigue},
    )


def _task(db, user, goal, minutes=30, status="pending", day=None):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day or date.today(),
        title="任务",
        type="study",
        duration_min=minutes,
        status=status,
        reason="测试",
        priority=1.0,
        source="plan",
    )
    db.add(task)
    db.flush()
    return task


def _mistake(db, user, goal, created_at=None):
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            question="错题",
            category="concept",
            created_at=created_at or datetime.utcnow(),
        )
    )
    db.flush()


# --------------------------------------------------------------------------
# 负荷分计算
# --------------------------------------------------------------------------


def test_compute_load_overload_keeps_only_one_light_task(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _task(db, user, goal, minutes=90)
    _task(db, user, goal, minutes=90)
    db.commit()
    _patch_state(monkeypatch, fatigue=90)

    result = compute_load(db, user, goal)

    # 90*0.55 + (180/90-1)*35 = 84.5，Python 银行家舍入后为 84
    assert result["score"] == 84
    assert result["level"] == "overload"
    assert result["recommended_tasks"] == 1
    assert result["recommended_minutes"] == 30
    assert result["advice"].startswith("认知负荷过高")
    assert result["factors"] == [
        "疲劳指数 90",
        "今日任务 2 个 / 180 分钟",
        "近 7 天错题率 0%",
        "准备度 70%",
    ]


def test_compute_load_high_level_splits_tasks(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _mistake(db, user, goal)
    _task(db, user, goal, minutes=30, status="done")
    db.commit()
    _patch_state(monkeypatch, fatigue=90)

    result = compute_load(db, user, goal)

    # 49.5 + 0 + 0.5*25 = 62
    assert result["score"] == 62
    assert result["level"] == "high"
    assert result["recommended_tasks"] == 1
    assert result["recommended_minutes"] == 45
    assert "负荷偏高" in result["advice"]
    assert result["factors"][2] == "近 7 天错题率 50%"


def test_compute_load_optimal_keeps_current_plan(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _task(db, user, goal)
    db.commit()
    _patch_state(monkeypatch, fatigue=55)

    result = compute_load(db, user, goal)

    # 30.25 => 30
    assert result["score"] == 30
    assert result["level"] == "optimal"
    assert result["recommended_tasks"] == 1
    assert result["recommended_minutes"] == 90
    assert "负荷适中" in result["advice"]


def test_compute_load_optimal_without_tasks_defaults_three(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=55)

    result = compute_load(db, user, goal)

    assert result["level"] == "optimal"
    assert result["recommended_tasks"] == 3


def test_compute_load_low_suggests_extra_challenge(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=10)

    result = compute_load(db, user, goal)

    assert result["score"] == 6
    assert result["level"] == "low"
    assert result["recommended_tasks"] == 3
    assert result["recommended_minutes"] == 110
    assert "负荷偏低" in result["advice"]


def test_compute_load_clamps_score_at_hundred(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    for _ in range(5):
        _task(db, user, goal, minutes=180)
    _mistake(db, user, goal)
    db.commit()
    _patch_state(monkeypatch, fatigue=100)

    result = compute_load(db, user, goal)

    assert result["score"] == 100
    assert result["level"] == "overload"


def test_compute_load_ignores_old_tasks_and_mistakes(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _task(db, user, goal, minutes=30, day=date.today())
    _mistake(db, user, goal, created_at=datetime(2020, 1, 1))
    db.commit()
    _patch_state(monkeypatch, fatigue=0)

    result = compute_load(db, user, goal)

    assert result["factors"][2] == "近 7 天错题率 0%"


def test_compute_load_real_dependencies_produce_consistent_shape(db, db_user_goal):
    user, goal = db_user_goal
    _task(db, user, goal, minutes=30)
    db.commit()

    result = compute_load(db, user, goal)

    assert 0 <= result["score"] <= 100
    assert result["level"] in ("overload", "high", "optimal", "low")
    assert len(result["factors"]) == 4
    assert isinstance(result["recommended_tasks"], int)
    assert isinstance(result["recommended_minutes"], int)


# --------------------------------------------------------------------------
# 自动与手动调节
# --------------------------------------------------------------------------


def test_apply_load_auto_reduce_when_overloaded(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=90)
    for _ in range(2):
        _task(db, user, goal, minutes=90)
    db.commit()

    result = apply_load(db, user, goal)

    assert result["action"] == "reduce"
    assert result["before"]["level"] == "overload"
    assert len(result["changes"]) == 1
    assert result["changes"][0]["kind"] == "defer"
    assert "顺延到" in result["changes"][0]["detail"]
    assert result["message"] == "已按认知负荷降载：顺延 1 个任务，保留 1 个最轻任务。"
    assert result["after"]["score"] < result["before"]["score"]

    db.expire_all()
    deferred = db.get(Task, result["changes"][0]["task_id"])
    assert deferred is not None
    assert deferred.day == date.today() + timedelta(days=1)
    # 降载文案必须写入任务原因，便于前端与历史记录解释自动调整
    assert deferred.reason.endswith("（风险救援：疲劳与负荷降载，自动顺延）")

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "cognitive_load")).one()
    assert evidence.subject == "认知负荷调节（reduce）"
    assert evidence.engine == "rule"
    assert json_action(evidence) == "reduce"


def json_action(evidence):
    import json

    return json.loads(evidence.payload)["action"]


def test_apply_load_auto_increase_adds_challenge_task(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=0)

    result = apply_load(db, user, goal)

    assert result["action"] == "increase"
    assert result["before"]["level"] == "low"
    assert result["changes"] == [
        {"kind": "increase", "detail": "加入迁移挑战任务", "task_id": None}
    ]
    assert result["message"] == "已加入 1 个 20 分钟迁移挑战任务。"

    created = db.scalars(select(Task).where(Task.source == "cognitive_load")).one()
    assert created.title == "迁移挑战：换情境应用"
    assert created.type == "practice"
    assert created.duration_min == 20
    assert created.priority == 2.8
    assert created.day == date.today()
    assert created.status == "pending"
    assert "认知负荷偏低" in created.reason

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "cognitive_load")).one()
    assert json_action(evidence) == "increase"


def test_apply_load_auto_keep_when_optimal(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=55)
    db.commit()

    result = apply_load(db, user, goal)

    assert result["action"] == "keep"
    assert result["changes"] == []
    assert result["message"] == "当前认知负荷适中，保持现有难度即可。"
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "cognitive_load")).one()
    assert json_action(evidence) == "keep"


def test_apply_load_explicit_keep_overrides_overload(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=90)
    for _ in range(2):
        _task(db, user, goal, minutes=90)
    db.commit()

    result = apply_load(db, user, goal, action="keep")

    assert result["action"] == "keep"
    assert result["message"] == "当前认知负荷适中，保持现有难度即可。"
    assert db.scalars(select(Task).where(Task.status == "pending")).all()


def test_apply_load_explicit_reduce_defers_extra_tasks(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=0)
    tasks = [_task(db, user, goal, minutes=20, status="pending") for _ in range(3)]
    tasks[0].priority = 9.0
    db.commit()

    result = apply_load(db, user, goal, action="reduce")

    assert result["action"] == "reduce"
    assert len(result["changes"]) == 2
    assert {item["kind"] for item in result["changes"]} == {"defer"}
    assert result["message"] == "已按认知负荷降载：顺延 2 个任务，保留 1 个最轻任务。"
    db.expire_all()
    kept = db.scalars(
        select(Task).where(
            Task.goal_id == goal.id, Task.day == date.today(), Task.status == "pending"
        )
    ).all()
    assert [task.id for task in kept] == [tasks[0].id]


def test_apply_load_unknown_action_falls_back_to_keep(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=90)
    for _ in range(2):
        _task(db, user, goal, minutes=90)
    db.commit()

    result = apply_load(db, user, goal, action="mystery")

    assert result["action"] == "mystery"
    assert result["message"] == "当前认知负荷适中，保持现有难度即可。"
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "cognitive_load")).one()
    assert json_action(evidence) == "mystery"


def test_apply_load_increase_recomputes_after_state(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=0)

    result = apply_load(db, user, goal, action="increase")

    assert result["after"]["factors"][1] == "今日任务 1 个 / 20 分钟"


def test_apply_load_reduce_with_single_task_uses_minimal_copy(db, db_user_goal, monkeypatch):
    """仅剩 1 个任务时降载不再顺延，文案应提示已足够精简。"""
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=90)
    _task(db, user, goal, minutes=30)
    db.commit()

    result = apply_load(db, user, goal, action="reduce")

    assert result["action"] == "reduce"
    assert result["changes"] == [
        {"kind": "keep", "detail": "今日任务已足够精简", "task_id": None}
    ]
    assert result["message"] == "当前任务已足够精简，保留 1 个最小任务即可，先恢复状态。"
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "cognitive_load")).one()
    assert evidence.subject == "认知负荷调节（reduce）"
    assert json_action(evidence) == "reduce"
    assert json.loads(evidence.payload)["action"] == "reduce"


def test_apply_load_reduce_keeps_lightest_task_and_marks_deferred_reason(
    db, db_user_goal, monkeypatch
):
    """降载保留 1 个最轻任务，被顺延任务写入统一降载文案。"""
    user, goal = db_user_goal
    _patch_state(monkeypatch, fatigue=95)
    light = _task(db, user, goal, minutes=15)
    heavy = _task(db, user, goal, minutes=120)
    light.priority = 9.0
    heavy.priority = 1.0
    db.commit()

    result = apply_load(db, user, goal, action="reduce")

    assert result["action"] == "reduce"
    assert result["changes"] == [
        {
            "kind": "defer",
            "detail": f"「{heavy.title}」顺延到 {(date.today() + timedelta(days=1)).isoformat()}",
            "task_id": heavy.id,
        }
    ]
    assert result["message"] == "已按认知负荷降载：顺延 1 个任务，保留 1 个最轻任务。"

    db.expire_all()
    kept = db.get(Task, light.id)
    deferred = db.get(Task, heavy.id)
    assert kept.status == "pending"
    assert kept.day == date.today()
    assert deferred.status == "pending"
    assert deferred.day == date.today() + timedelta(days=1)
    assert deferred.reason == "测试（风险救援：疲劳与负荷降载，自动顺延）"
