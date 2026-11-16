"""学习数字孪生（twin）单元测试。"""

from datetime import date, timedelta

from app.models import (
    KnowledgeGap,
    KnowledgePoint,
    LearningExperiment,
    Mastery,
    Mistake,
    Task,
)
from app.services.twin import build_twin


def _point(db, goal, name, parent_id=None, weight=1.0):
    point = KnowledgePoint(goal_id=goal.id, name=name, parent_id=parent_id, weight=weight)
    db.add(point)
    db.flush()
    return point


def _task(db, user, goal, day, status="pending", minutes=30):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        day=day,
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


# --------------------------------------------------------------------------
# build_twin
# --------------------------------------------------------------------------


def test_build_twin_aggregates_matrix_distribution_trend_and_ranking(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    root = _point(db, goal, "听力", weight=1.5)
    child = _point(db, goal, "短对话", root.id, weight=1.2)
    db.add(Mastery(user_id=user.id, kp_id=child.id, value=0.5))
    for category in ("concept", "concept", "method"):
        db.add(
            Mistake(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=child.id,
                question="题目",
                user_answer="答案",
                correct_answer="正确",
                category=category,
            )
        )
    db.add(
        KnowledgeGap(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=child.id,
            status="verified",
            evidence="验证题答错",
        )
    )
    _task(db, user, goal, today, "done", 40)
    _task(db, user, goal, today, "skipped", 30)
    _task(db, user, goal, today, "pending", 20)
    _task(db, user, goal, today - timedelta(days=10), "done", 25)
    db.add(
        LearningExperiment(
            user_id=user.id,
            goal_id=goal.id,
            strategy="read",
            status="finished",
            days=3,
            start_date=today,
            end_date=today,
            pre_mastery=0.2,
            post_mastery=0.5,
        )
    )
    db.commit()

    twin = build_twin(db, user, goal, today=today)

    matrix = {item["kp_id"]: item for item in twin["knowledge_matrix"]}
    assert len(matrix) == 2
    assert matrix[child.id]["parent"] == "听力"
    assert matrix[child.id]["mastery"] == 0.5
    assert matrix[child.id]["mistake_count"] == 3
    assert matrix[child.id]["status"] == "verified"
    assert matrix[root.id]["status"] == "normal"

    distribution = {item["category"]: item for item in twin["mistake_distribution"]}
    assert [item["category"] for item in twin["mistake_distribution"]] == [
        "concept",
        "method",
        "careless",
        "time",
    ]
    assert distribution["concept"]["count"] == 2
    assert distribution["method"]["count"] == 1
    assert distribution["careless"]["count"] == 0
    assert distribution["time"]["label"] == "时间不够"

    trend = twin["behavior_trend"]
    assert len(trend) == 8
    latest = trend[-1]
    assert latest["week_start"] == today - timedelta(days=6)
    assert latest["done"] == 1
    assert latest["minutes"] == 40
    # 跳过任务不计入判定，完成 1 / 判定 2
    assert latest["completion_rate"] == 0.5
    older = trend[6]
    assert older["done"] == 1
    assert older["minutes"] == 25
    assert older["completion_rate"] == 1.0

    assert twin["strategy_ranking"] == [
        {"strategy": "read", "label": "精读理解", "avg_gain": 0.3, "experiments": 1}
    ]


def test_build_twin_without_data_returns_empty_structure(db, db_user_goal):
    user, goal = db_user_goal

    twin = build_twin(db, user, goal)

    assert twin["knowledge_matrix"] == []
    assert len(twin["mistake_distribution"]) == 4
    assert all(item["count"] == 0 for item in twin["mistake_distribution"])
    assert len(twin["behavior_trend"]) == 8
    assert all(
        item["done"] == 0 and item["minutes"] == 0 and item["completion_rate"] == 0.0
        for item in twin["behavior_trend"]
    )
    assert twin["strategy_ranking"] == []