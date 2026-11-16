from datetime import date, timedelta


def test_dashboard_without_goals(api, auth):
    response = api("GET", "/api/dashboard", token=auth["token"])
    assert response.status_code == 200
    body = response.json()
    assert body["goal"] is None
    assert body["today_tasks"] == []
    assert body["today_minutes"] == 0
    assert body["rhythm"] is None
    assert "欢迎来到学迹" in body["coach_message"]
    assert body["server_date"] == date.today().isoformat()


def test_dashboard_with_goal_and_plan(api, auth, goal, imported_points):
    token = auth["token"]
    plan = api("POST", f"/api/goals/{goal['id']}/plan", token=token, json={"days": 2})
    assert plan.status_code == 200

    response = api("GET", "/api/dashboard", token=token)
    assert response.status_code == 200
    body = response.json()
    assert body["goal"]["id"] == goal["id"]
    assert len(body["today_tasks"]) == 3
    assert body["today_minutes"] == 90
    assert body["streak"] == 0
    assert len(body["mastery"]) == 10
    assert len(body["weak_points"]) == 5
    assert body["mistake_count_7d"] == 0
    assert body["recent_mistakes"] == []
    assert body["latest_changes"] == []
    assert body["rhythm"]["sampled_tasks"] == 3
    assert body["rhythm"]["habit"] == "节奏待建立"
    assert "今天还剩 3 个任务" in body["coach_message"]


def test_dashboard_marks_done_and_updates_streak(api, auth, goal, imported_points):
    token = auth["token"]
    plan = api("POST", f"/api/goals/{goal['id']}/plan", token=token, json={"days": 1})
    for task in plan.json()["tasks"]:
        api("PATCH", f"/api/goals/tasks/{task['id']}", token=token, json={"status": "done"})

    body = api("GET", "/api/dashboard", token=token).json()
    assert body["streak"] == 1
    assert all(task["status"] == "done" for task in body["today_tasks"])
    assert "全部完成" in body["coach_message"]


def test_dashboard_accepts_goal_id(api, auth, goal):
    token = auth["token"]
    second = api(
        "POST",
        "/api/goals",
        token=token,
        json={
            "exam_name": "考研数学",
            "exam_date": (date.today() + timedelta(days=60)).isoformat(),
            "daily_minutes": 120,
        },
    )
    other_goal = second.json()
    body = api("GET", "/api/dashboard", token=token, params={"goal_id": other_goal["id"]}).json()
    assert body["goal"]["id"] == other_goal["id"]
    assert body["today_tasks"] == []


def test_dashboard_unknown_goal_is_rejected(api, auth):
    response = api("GET", "/api/dashboard", token=auth["token"], params={"goal_id": 99999})
    assert response.status_code == 404


def test_rhythm_endpoint(api, auth, goal):
    token = auth["token"]
    response = api("GET", f"/api/goals/{goal['id']}/rhythm", token=token)
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 28
    assert body["sampled_tasks"] == 0
    assert len(body["periods"]) == 4
    assert body["tasks_per_day"] == 3

    ten_days = api("GET", f"/api/goals/{goal['id']}/rhythm?days=10", token=token)
    assert ten_days.json()["window_days"] == 10

    invalid_high = api("GET", f"/api/goals/{goal['id']}/rhythm?days=61", token=token)
    assert invalid_high.status_code == 422
    invalid_low = api("GET", f"/api/goals/{goal['id']}/rhythm?days=1", token=token)
    assert invalid_low.status_code == 422


def test_rhythm_counts_done_tasks(api, auth, goal, imported_points):
    token = auth["token"]
    plan = api("POST", f"/api/goals/{goal['id']}/plan", token=token, json={"days": 1})
    for task in plan.json()["tasks"]:
        api("PATCH", f"/api/goals/tasks/{task['id']}", token=token, json={"status": "done"})

    body = api("GET", f"/api/goals/{goal['id']}/rhythm", token=token).json()
    assert body["sampled_tasks"] == 3
    assert body["completion_rate"] == 1.0
    assert body["done_minutes"] == 3 * 30
    assert body["on_time_rate"] == 1.0
    assert body["peak_period"] in {"morning", "afternoon", "evening", "night"} or body["peak_period"] is None


def test_rhythm_requires_authentication(api, goal):
    assert api("GET", f"/api/goals/{goal['id']}/rhythm").status_code == 401