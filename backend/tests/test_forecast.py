"""冲刺预测模块单元测试：掌握度模拟、所需时长反推与冲刺接口。"""

from datetime import date, timedelta

import pytest

from app.models import KnowledgePoint, Mastery
from app.services.forecast import (
    DAILY_COVER_POINTS,
    DAILY_FORGET,
    GAIN_PER_TOUCH,
    _simulate,
    build_forecast,
)
from tests.conftest import add_points


def _set_points(db, user, goal, values, parent=None):
    points = []
    for index, value in enumerate(values):
        point = KnowledgePoint(
            goal_id=goal.id,
            name=f"知识点{index}",
            weight=1.0 + index * 0.5,
            parent_id=parent.id if parent else None,
        )
        db.add(point)
        db.flush()
        if value is not None:
            db.add(Mastery(user_id=user.id, kp_id=point.id, value=value))
        points.append(point)
    db.commit()
    return points


# --------------------------------------------------------------------------
# _simulate 纯函数
# --------------------------------------------------------------------------


def test_simulate_without_mastery_returns_empty_curve():
    result = _simulate([], [], daily_minutes=60, days=10, today=date.today())
    assert result == (0.0, [])


def test_simulate_applies_forgetting_and_gain_once_per_day():
    today = date.today()
    final_value, curve = _simulate([0.0], [1.0], daily_minutes=20, days=10, today=today)

    expected = 0.0
    for _ in range(10):
        expected = expected * DAILY_FORGET
        expected = expected + GAIN_PER_TOUCH * (1 - expected)
    expected = round(expected, 4)
    assert final_value == pytest.approx(expected, abs=1e-4)
    assert len(curve) == 10
    assert curve[0]["day"] == today + timedelta(days=1)
    assert curve[-1]["day"] == today + timedelta(days=10)
    assert curve[-1]["mastery"] == final_value


def test_simulate_prioritises_weakest_weighted_point():
    today = date.today()
    final_value, curve = _simulate([0.9, 0.0], [1.0, 1.0], daily_minutes=20, days=1, today=today)

    weakened = 0.9 * DAILY_FORGET
    gained = GAIN_PER_TOUCH
    expected = round((weakened + gained) / 2, 4)
    assert final_value == pytest.approx(expected, abs=1e-6)
    assert curve == [{"day": today + timedelta(days=1), "mastery": expected}]


def test_simulate_never_exceeds_full_mastery():
    today = date.today()
    final_value, curve = _simulate([1.0], [1.0], daily_minutes=600, days=5, today=today)

    assert 0.98 < final_value < 1.0
    assert all(item["mastery"] <= 1.0 for item in curve)


def test_simulate_cover_uses_daily_minutes_buckets():
    today = date.today()
    # 20 分钟覆盖 1 个点，40 分钟覆盖 2 个点
    one_point, _ = _simulate([0.0, 0.0], [1.0, 1.0], daily_minutes=DAILY_COVER_POINTS, days=1, today=today)
    two_points, _ = _simulate(
        [0.0, 0.0], [1.0, 1.0], daily_minutes=DAILY_COVER_POINTS * 2, days=1, today=today
    )

    assert one_point == 0.06
    assert two_points == pytest.approx(GAIN_PER_TOUCH, abs=1e-6)
    assert one_point < two_points


def test_simulate_curve_sampling_every_n_days():
    today = date.today()
    _, curve = _simulate([0.0], [1.0], daily_minutes=90, days=30, today=today)

    assert len(curve) == 10
    assert curve[0]["day"] == today + timedelta(days=3)
    assert curve[-1]["day"] == today + timedelta(days=30)


# --------------------------------------------------------------------------
# build_forecast
# --------------------------------------------------------------------------


def test_build_forecast_without_points_returns_guidance(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()

    result = build_forecast(db, user, goal, today=today)

    assert result == {
        "current_mastery": 0.0,
        "projected_mastery": 0.0,
        "days_left": 30,
        "target_mastery": 0.7,
        "required_daily_minutes": None,
        "recommendation": "还没有知识点，先导入资料再模拟冲刺效果。",
        "curve": [],
        "scenarios": [],
    }


def test_build_forecast_only_counts_leaf_points(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    parent = KnowledgePoint(goal_id=goal.id, name="阅读", weight=2.0)
    db.add(parent)
    db.flush()
    child = KnowledgePoint(goal_id=goal.id, name="仔细阅读", weight=1.5, parent_id=parent.id)
    db.add(child)
    db.flush()
    db.add(Mastery(user_id=user.id, kp_id=child.id, value=1.0))
    db.commit()

    result = build_forecast(db, user, goal, today=today)

    assert result["current_mastery"] == 1.0
    assert result["target_mastery"] == 0.9


def test_build_forecast_falls_back_to_all_points_for_self_parent(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    point = KnowledgePoint(goal_id=goal.id, name="循环知识点", weight=1.0)
    db.add(point)
    db.flush()
    point.parent_id = point.id
    db.commit()

    result = build_forecast(db, user, goal, today=today)

    assert result["current_mastery"] == 0.0
    assert len(result["scenarios"]) == 3


def test_build_forecast_meets_target_with_current_pace(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _set_points(db, user, goal, [0.9, 0.9])

    result = build_forecast(db, user, goal, daily_minutes=20, today=today)

    assert result["current_mastery"] == 0.9
    assert result["target_mastery"] == 0.9
    assert result["projected_mastery"] >= result["target_mastery"]
    # required 搜索独立于 projected，当前节奏即可达标
    assert result["required_daily_minutes"] == 20
    assert "保持节奏即可" in result["recommendation"]


def test_build_forecast_recommends_more_daily_minutes(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today + timedelta(days=10)
    goal.daily_minutes = 20
    db.commit()
    _set_points(db, user, goal, [0.0, 0.0])

    result = build_forecast(db, user, goal, today=today)

    assert result["current_mastery"] == 0.0
    assert result["projected_mastery"] < result["target_mastery"]
    assert result["required_daily_minutes"] == 40
    assert "建议每天提高到约 40 分钟" in result["recommendation"]

    scenarios = {item["label"]: item for item in result["scenarios"]}
    assert list(scenarios) == ["当前节奏", "减负 -30 分钟", "冲刺 +30 分钟"]
    assert scenarios["当前节奏"]["daily_minutes"] == 20
    assert scenarios["当前节奏"]["feasible"] is False
    assert scenarios["减负 -30 分钟"]["daily_minutes"] == 20
    assert scenarios["冲刺 +30 分钟"]["daily_minutes"] == 50
    assert scenarios["冲刺 +30 分钟"]["feasible"] is True


def test_build_forecast_reports_impossible_target(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today + timedelta(days=1)
    db.commit()
    _set_points(db, user, goal, [0.0, 0.0])

    result = build_forecast(db, user, goal, daily_minutes=20, today=today)

    assert result["days_left"] == 1
    assert result["projected_mastery"] == 0.06
    assert result["required_daily_minutes"] is None
    assert "即使每天 600 分钟" in result["recommendation"]
    assert "预计也只能达到 6%" in result["recommendation"]


def test_build_forecast_clamps_scenarios_and_past_exam_date(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today - timedelta(days=5)
    goal.daily_minutes = 600
    db.commit()
    _set_points(db, user, goal, [0.0, 0.0])

    result = build_forecast(db, user, goal, daily_minutes=60, today=today)

    assert result["days_left"] == 0
    assert [item["daily_minutes"] for item in result["scenarios"]] == [60, 30, 90]
    assert result["curve"][-1]["day"] == today + timedelta(days=1)


def test_build_forecast_caps_sprint_minutes_at_600(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    goal.exam_date = today + timedelta(days=5)
    db.commit()
    _set_points(db, user, goal, [0.0])

    result = build_forecast(db, user, goal, daily_minutes=600, today=today)

    scenarios = {item["label"]: item["daily_minutes"] for item in result["scenarios"]}
    assert scenarios["当前节奏"] == 600
    assert scenarios["减负 -30 分钟"] == 570
    assert scenarios["冲刺 +30 分钟"] == 600


def test_build_forecast_curve_uses_ten_samples_for_thirty_days(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _set_points(db, user, goal, [0.0])

    result = build_forecast(db, user, goal, today=today)

    assert len(result["curve"]) == 10
    assert result["curve"][0]["day"] == today + timedelta(days=3)
    assert result["curve"][-1]["day"] == today + timedelta(days=30)
    assert all(0.0 <= item["mastery"] <= 1.0 for item in result["curve"])


def test_build_forecast_daily_minutes_argument_overrides_goal(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _set_points(db, user, goal, [0.0])

    result = build_forecast(db, user, goal, daily_minutes=25, today=today)

    assert result["scenarios"][0]["daily_minutes"] == 25
    assert "每天 25 分钟" in result["recommendation"]


# --------------------------------------------------------------------------
# API：/goals/{id}/forecast 与 /apply-forecast
# --------------------------------------------------------------------------


def test_forecast_endpoint_returns_plan(api, auth, goal, imported_points):
    token = auth["token"]
    response = api("GET", f"/api/goals/{goal['id']}/forecast", token=token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days_left"] == 40
    assert body["current_mastery"] == 0.0
    assert len(body["curve"]) == 10
    assert len(body["scenarios"]) == 3
    assert body["target_mastery"] == 0.7

    custom = api(
        "GET",
        f"/api/goals/{goal['id']}/forecast",
        token=token,
        params={"daily_minutes": 20},
    )
    assert custom.status_code == 200
    assert custom.json()["scenarios"][0]["daily_minutes"] == 20


def test_forecast_endpoint_validates_daily_minutes(api, auth, goal):
    for invalid in (19, 601):
        response = api(
            "GET",
            f"/api/goals/{goal['id']}/forecast",
            token=auth["token"],
            params={"daily_minutes": invalid},
        )
        assert response.status_code == 422


def test_forecast_endpoint_requires_authentication(api, goal):
    assert api("GET", f"/api/goals/{goal['id']}/forecast").status_code == 401


def test_forecast_endpoint_rejects_unknown_goal(api, auth):
    assert api("GET", "/api/goals/99999/forecast", token=auth["token"]).status_code == 404


def test_apply_forecast_updates_goal_and_regenerates_today(api, auth, goal, imported_points):
    token = auth["token"]
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/apply-forecast",
        token=token,
        json={"daily_minutes": 60},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["goal"]["daily_minutes"] == 60
    assert body["forecast"]["current_mastery"] == 0.0
    assert body["forecast"]["scenarios"][0]["daily_minutes"] == 60
    assert isinstance(body["changes"], list)
    assert body["auto_adjust"]["days_left"] == 40
    assert body["auto_adjust"]["adjusted"] is True
    assert "自动生成今日计划" in body["auto_adjust"]["summary"]

    refreshed = api("GET", "/api/goals", token=token)
    assert refreshed.status_code == 200
    updated = [item for item in refreshed.json() if item["id"] == goal["id"]][0]
    assert updated["daily_minutes"] == 60


def test_apply_forecast_validates_payload(api, auth, goal):
    token = auth["token"]
    too_small = api(
        "POST",
        f"/api/goals/{goal['id']}/apply-forecast",
        token=token,
        json={"daily_minutes": 19},
    )
    assert too_small.status_code == 422
    too_large = api(
        "POST",
        f"/api/goals/{goal['id']}/apply-forecast",
        token=token,
        json={"daily_minutes": 601},
    )
    assert too_large.status_code == 422


def test_apply_forecast_rejects_unknown_goal(api, auth):
    response = api(
        "POST",
        "/api/goals/99999/apply-forecast",
        token=auth["token"],
        json={"daily_minutes": 60},
    )
    assert response.status_code == 404

def test_build_forecast_days_left_moves_with_date(db, db_user_goal):
    """时间必须自动变换：把 today 往后拨，倒计时递减、曲线起点同步后移。"""
    user, goal = db_user_goal
    _set_points(db, user, goal, [0.2, 0.4])
    today = date.today()

    day0 = build_forecast(db, user, goal, today=today)
    day7 = build_forecast(db, user, goal, today=today + timedelta(days=7))

    assert day0["days_left"] == 30
    assert day7["days_left"] == 23
    assert day0["curve"] and day7["curve"]
    # 预测窗口是 30 天，today 后移 7 天，曲线起点也应后移 7 天
    first0, first7 = day0["curve"][0]["day"], day7["curve"][0]["day"]
    first0 = date.fromisoformat(first0) if isinstance(first0, str) else first0
    first7 = date.fromisoformat(first7) if isinstance(first7, str) else first7
    # 曲线按窗口等距采样，位移应接近 7 天（允许一格采样误差），关键是绝不原地不动
    assert 5 <= (first7 - first0).days <= 7
