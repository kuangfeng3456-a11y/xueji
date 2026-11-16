"""学情洞察模块单元测试：热力图、能力雷达、疲劳指数与成就徽章。"""

from datetime import date, datetime, time, timedelta

from app.models import FocusSession, Mastery, Mistake, Task, Violation
from app.services.insights import (
    build_achievements,
    build_fatigue,
    build_heatmap,
    build_insights,
    build_radar,
)
from tests.conftest import add_points


def _task(db, user, goal, day, status="pending", minutes=30, kp_id=None):
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=kp_id,
        day=day,
        title="测试任务",
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


def _session(db, user, goal, started_at, status="completed", minutes=30, leaves=0):
    session = FocusSession(
        user_id=user.id,
        goal_id=goal.id,
        planned_minutes=max(minutes, 1),
        actual_minutes=minutes,
        status=status,
        leaves=leaves,
        started_at=started_at,
    )
    db.add(session)
    db.flush()
    return session


# --------------------------------------------------------------------------
# build_heatmap
# --------------------------------------------------------------------------


def test_heatmap_empty_window_is_all_zero(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()

    heatmap = build_heatmap(db, user.id, goal.id, weeks=4, today=today)

    assert len(heatmap) == 28
    assert heatmap[0]["day"] == today - timedelta(days=27)
    assert heatmap[-1]["day"] == today
    assert all(
        item["minutes"] == 0
        and item["done"] == 0
        and item["focus_minutes"] == 0
        and item["level"] == 0
        for item in heatmap
    )


def test_heatmap_levels_follow_done_minutes_thresholds(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    cases = [(0, 20, 1), (1, 30, 2), (2, 60, 3), (3, 90, 4)]
    for offset, minutes, _level in cases:
        _task(db, user, goal, today - timedelta(days=offset), "done", minutes)
    _task(db, user, goal, today - timedelta(days=5), "pending", 120)
    _task(db, user, goal, today - timedelta(days=6), "skipped", 60)
    db.commit()

    heatmap = build_heatmap(db, user.id, goal.id, today=today)
    by_day = {item["day"]: item for item in heatmap}

    for offset, minutes, level in cases:
        item = by_day[today - timedelta(days=offset)]
        assert item["minutes"] == minutes
        assert item["done"] == 1
        assert item["level"] == level

    assert by_day[today - timedelta(days=5)]["level"] == 0
    assert by_day[today - timedelta(days=5)]["minutes"] == 0
    assert by_day[today - timedelta(days=6)]["level"] == 0


def test_heatmap_aggregates_multiple_done_tasks_per_day(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _task(db, user, goal, today, "done", 25)
    _task(db, user, goal, today, "done", 35)
    db.commit()

    item = build_heatmap(db, user.id, goal.id, weeks=1, today=today)[-1]

    assert item["minutes"] == 60
    assert item["done"] == 2
    assert item["level"] == 3


def test_heatmap_counts_completed_focus_with_utc_offset(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    # 22:00 UTC + 8 小时 => 次日 06:00，计入今天
    _session(
        db,
        user,
        goal,
        datetime.combine(today - timedelta(days=1), time(22, 0)),
        "completed",
        25,
    )
    # 中断的专注不计入
    _session(db, user, goal, datetime.combine(today, time(10, 0)), "aborted", 50)
    # 23:00 UTC + 8 小时 => 明天，落在窗口外
    _session(db, user, goal, datetime.combine(today, time(23, 0)), "completed", 30)
    db.commit()

    heatmap = build_heatmap(db, user.id, goal.id, weeks=2, today=today)
    by_day = {item["day"]: item for item in heatmap}

    assert by_day[today]["focus_minutes"] == 25
    assert by_day[today]["minutes"] == 0
    assert by_day[today - timedelta(days=1)]["focus_minutes"] == 0


# --------------------------------------------------------------------------
# build_radar
# --------------------------------------------------------------------------


def test_radar_computes_five_dimensions(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    points = add_points(db, goal, names=("听力", "阅读"))
    db.add_all(
        [
            Mastery(user_id=user.id, kp_id=points[0].id, value=0.2),
            Mastery(user_id=user.id, kp_id=points[1].id, value=0.6),
        ]
    )
    for offset in (0, 1, 3):
        _task(db, user, goal, today - timedelta(days=offset), "done", 30)
    _task(db, user, goal, today - timedelta(days=2), "skipped", 30)
    for offset in range(7):
        _session(
            db,
            user,
            goal,
            datetime.combine(today - timedelta(days=offset), time(10, 0)),
            "completed",
            20,
        )
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=points[0].id,
            question="题目",
            user_answer="答案",
            correct_answer="正确答案",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db.commit()

    radar = build_radar(db, user.id, goal.id, today=today)
    by_key = {item["key"]: item for item in radar}

    assert [item["key"] for item in radar] == [
        "mastery",
        "rhythm",
        "focus",
        "accuracy",
        "persistence",
    ]
    assert by_key["mastery"]["label"] == "知识掌握"
    assert by_key["mastery"]["value"] == 0.4
    assert by_key["rhythm"]["value"] == 1.0
    assert by_key["focus"]["value"] == 1.0
    assert by_key["accuracy"]["value"] == 0.6667
    assert by_key["persistence"]["value"] == 0.1429


def test_radar_without_data_keeps_accuracy_at_one(db, db_user_goal):
    user, goal = db_user_goal
    radar = build_radar(db, user.id, goal.id, today=date.today())
    by_key = {item["key"]: item for item in radar}

    assert len(radar) == 5
    assert by_key["mastery"]["value"] == 0.0
    assert by_key["rhythm"]["value"] == 0.0
    assert by_key["focus"]["value"] == 0.0
    assert by_key["accuracy"]["value"] == 1.0
    assert by_key["persistence"]["value"] == 0.0


def test_radar_accuracy_drops_when_mistakes_outnumber_done_tasks(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    point = add_points(db, goal, names=("听力",))[0]
    for _ in range(2):
        db.add(
            Mistake(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=point.id,
                question="题目",
                user_answer="答案",
                correct_answer="正确答案",
                created_at=datetime.utcnow(),
            )
        )
    db.commit()

    radar = build_radar(db, user.id, goal.id, today=today)
    accuracy = [item for item in radar if item["key"] == "accuracy"][0]

    assert accuracy["value"] == 0.0


def test_radar_focus_value_is_capped_at_one(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    for offset in range(14):
        _session(
            db,
            user,
            goal,
            datetime.combine(today - timedelta(days=offset), time(9, 0)),
            "completed",
            10,
        )
    db.commit()

    radar = build_radar(db, user.id, goal.id, today=today)
    focus = [item for item in radar if item["key"] == "focus"][0]

    assert focus["value"] == 1.0


# --------------------------------------------------------------------------
# build_fatigue
# --------------------------------------------------------------------------


def test_fatigue_without_signals_is_low(db, db_user_goal):
    user, goal = db_user_goal
    fatigue = build_fatigue(db, user.id, goal.id, today=date.today())

    assert fatigue["score"] == 0
    assert fatigue["level"] == "low"
    assert fatigue["factors"] == ["暂无明显疲劳信号"]
    assert fatigue["suggested_tasks_per_day"] == 3
    assert "状态良好" in fatigue["advice"]


def test_fatigue_combines_leaves_aborts_and_overwork(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _session(
        db,
        user,
        goal,
        datetime.combine(today - timedelta(days=1), time(10, 0)),
        "completed",
        200,
        leaves=3,
    )
    _session(
        db,
        user,
        goal,
        datetime.combine(today, time(10, 0)),
        "aborted",
        30,
    )
    db.commit()

    fatigue = build_fatigue(db, user.id, goal.id, today=today)

    assert fatigue["score"] == 40
    assert fatigue["level"] == "medium"
    assert fatigue["suggested_tasks_per_day"] == 2
    assert "疲劳开始累积" in fatigue["advice"]
    assert any("离开专注页面 3 次" in item for item in fatigue["factors"])
    assert any("1 次专注中断" in item for item in fatigue["factors"])
    assert any("累计专注 200 分钟" in item for item in fatigue["factors"])


def test_fatigue_is_capped_at_one_hundred(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    _session(
        db,
        user,
        goal,
        datetime.combine(today, time(9, 0)),
        "completed",
        200,
        leaves=10,
    )
    for _ in range(2):
        _session(db, user, goal, datetime.combine(today, time(11, 0)), "aborted", 10)
    db.commit()

    fatigue = build_fatigue(db, user.id, goal.id, today=today)

    assert fatigue["score"] == 100
    assert fatigue["level"] == "high"
    assert fatigue["suggested_tasks_per_day"] == 1
    assert "疲劳指数偏高" in fatigue["advice"]


def test_fatigue_reacts_to_mistakes_violations_and_streak(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    point = add_points(db, goal, names=("听力",))[0]
    for _ in range(3):
        db.add(
            Mistake(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=point.id,
                question="题目",
                user_answer="答案",
                correct_answer="正确答案",
                created_at=datetime.utcnow() - timedelta(days=1),
            )
        )
    for offset in (1, 2):
        db.add(
            Violation(
                user_id=user.id,
                goal_id=goal.id,
                day=today - timedelta(days=offset),
                kind="abort",
                detail="退出专注",
            )
        )
    for offset in range(1, 13):
        _task(db, user, goal, today - timedelta(days=offset), "done", 20)
    db.commit()

    fatigue = build_fatigue(db, user.id, goal.id, today=today)

    assert fatigue["score"] == 32
    assert fatigue["level"] == "medium"
    assert any("错题数从上周 0 道增至 3 道" in item for item in fatigue["factors"])
    assert any("2 次违约" in item for item in fatigue["factors"])
    assert any("连续学习 12 天" in item for item in fatigue["factors"])


# --------------------------------------------------------------------------
# build_achievements
# --------------------------------------------------------------------------


def test_achievements_unlock_by_progress(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    points = add_points(db, goal, names=("听力", "阅读"))
    db.add_all(
        [
            Mastery(user_id=user.id, kp_id=point.id, value=0.65)
            for point in points
        ]
    )
    for offset in range(10):
        _task(db, user, goal, today - timedelta(days=offset), "done", 30)
    for offset in range(5):
        _session(
            db,
            user,
            goal,
            datetime.combine(today - timedelta(days=offset), time(9, 0)),
            "completed",
            25,
        )
    db.commit()

    badges = {item["code"]: item for item in build_achievements(db, user.id, goal.id, today=today)}

    assert len(badges) == 8
    assert badges["first_task"]["unlocked"] is True
    assert badges["first_task"]["progress"] == 1
    assert badges["streak_7"]["unlocked"] is True
    assert badges["streak_7"]["progress"] == 7
    assert badges["streak_15"]["unlocked"] is False
    assert badges["streak_15"]["progress"] == 10
    assert badges["tasks_50"]["unlocked"] is False
    assert badges["tasks_50"]["progress"] == 10
    assert badges["mastery_60"]["unlocked"] is True
    assert badges["mastery_60"]["progress"] == 60
    assert badges["focus_5"]["unlocked"] is True
    assert badges["focus_5"]["progress"] == 5
    assert badges["perfect_3"]["unlocked"] is True
    assert badges["perfect_3"]["progress"] == 3
    assert badges["clear_week"]["unlocked"] is True
    assert badges["clear_week"]["progress"] == 1


def test_achievements_without_data_only_self_discipline_unlocked(db, db_user_goal):
    user, goal = db_user_goal
    badges = {item["code"]: item for item in build_achievements(db, user.id, goal.id, today=date.today())}

    assert len(badges) == 8
    for code in (
        "first_task",
        "streak_7",
        "streak_15",
        "tasks_50",
        "mastery_60",
        "focus_5",
        "perfect_3",
    ):
        assert badges[code]["unlocked"] is False
        assert badges[code]["progress"] == 0
    # 没有违约记录时，“自律一周”默认达成
    assert badges["clear_week"]["unlocked"] is True
    assert badges["clear_week"]["progress"] == 1


def test_achievements_perfect_days_ignore_pending_and_skipped(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    # 今天有一个未完成任务，不算满勤
    _task(db, user, goal, today, "done", 30)
    _task(db, user, goal, today, "pending", 30)
    # 昨天全部跳过，也不算满勤
    _task(db, user, goal, today - timedelta(days=1), "skipped", 30)
    # 近 7 天有违约
    db.add(
        Violation(
            user_id=user.id,
            goal_id=goal.id,
            day=today - timedelta(days=1),
            kind="abort",
            detail="退出专注",
        )
    )
    db.commit()

    badges = {item["code"]: item for item in build_achievements(db, user.id, goal.id, today=today)}

    assert badges["perfect_3"]["progress"] == 0
    assert badges["perfect_3"]["unlocked"] is False
    assert badges["clear_week"]["progress"] == 0
    assert badges["clear_week"]["unlocked"] is False


# --------------------------------------------------------------------------
# build_insights 聚合
# --------------------------------------------------------------------------


def test_build_insights_aggregates_all_sections(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    point = add_points(db, goal, names=("听力",))[0]
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=0.5))
    for offset, minutes in ((0, 60), (1, 30)):
        _task(db, user, goal, today - timedelta(days=offset), "done", minutes)
    db.commit()

    result = build_insights(db, user.id, goal.id, today=today)

    assert len(result["heatmap"]) == 84
    assert len(result["radar"]) == 5
    assert result["radar_score"] == 0.5286
    assert result["fatigue"]["level"] == "low"
    assert len(result["achievements"]) == 8
    assert result["streak"] == 2
    assert result["total_minutes"] == 90
    assert result["active_days"] == 2
    heatmap_today = result["heatmap"][-1]
    assert heatmap_today["minutes"] == 60
    assert heatmap_today["level"] == 3


# --------------------------------------------------------------------------
# API：/goals/{id}/insights
# --------------------------------------------------------------------------


def test_insights_endpoint_returns_all_sections(api, auth, goal, imported_points):
    response = api("GET", f"/api/goals/{goal['id']}/insights", token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["heatmap"]) == 84
    assert len(body["radar"]) == 5
    assert [item["key"] for item in body["radar"]] == [
        "mastery",
        "rhythm",
        "focus",
        "accuracy",
        "persistence",
    ]
    assert body["radar_score"] == 0.2
    assert body["fatigue"]["level"] == "low"
    assert len(body["achievements"]) == 8
    assert body["streak"] == 0
    assert body["total_minutes"] == 0
    assert body["active_days"] == 0


def test_insights_endpoint_reflects_completed_tasks(api, auth, goal, imported_points):
    token = auth["token"]
    plan = api("POST", f"/api/goals/{goal['id']}/plan", token=token, json={"days": 1})
    assert plan.status_code == 200, plan.text
    tasks = plan.json()["tasks"]
    assert len(tasks) == 3
    for task in tasks:
        done = api("PATCH", f"/api/goals/tasks/{task['id']}", token=token, json={"status": "done"})
        assert done.status_code == 200, done.text

    response = api("GET", f"/api/goals/{goal['id']}/insights", token=token)
    assert response.status_code == 200
    body = response.json()
    assert body["active_days"] == 1
    assert body["total_minutes"] == 90
    assert body["streak"] == 1
    assert body["radar"][1]["value"] == 1.0
    first_task = [item for item in body["achievements"] if item["code"] == "first_task"][0]
    assert first_task["unlocked"] is True


def test_insights_endpoint_requires_authentication(api, goal):
    assert api("GET", f"/api/goals/{goal['id']}/insights").status_code == 401


def test_insights_endpoint_rejects_unknown_goal(api, auth):
    response = api("GET", "/api/goals/99999/insights", token=auth["token"])
    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"