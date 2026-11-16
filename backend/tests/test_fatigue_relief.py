"""疲劳降载接口单元测试：保留最高优先级任务、顺延与取消。"""

import json
from datetime import date, timedelta

from app.models import Goal, ReplanLog, Task


def _plan_today(api, token, goal_id):
    response = api("POST", f"/api/goals/{goal_id}/plan", token=token, json={"days": 1})
    assert response.status_code == 200, response.text
    return response.json()["tasks"]


def test_rest_without_tasks_returns_concise_summary(api, auth, goal):
    response = api("POST", f"/api/goals/{goal['id']}/rest", token=auth["token"])

    assert response.status_code == 200, response.text
    assert response.json() == {
        "moved": 0,
        "kept": 0,
        "summary": "今日任务已经足够精简，先把剩下的完成即可。",
    }


def test_rest_keeps_highest_priority_task_and_defers_rest(api, auth, goal, imported_points, db):
    token = auth["token"]
    tasks = _plan_today(api, token, goal["id"])
    assert len(tasks) == 3
    highest = max(tasks, key=lambda item: item["priority"])
    today = date.today()

    response = api("POST", f"/api/goals/{goal['id']}/rest", token=token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kept"] == 1
    assert body["moved"] == 2
    assert f"今天只保留「{highest['title']}」" in body["summary"]
    assert "其余 2 个任务顺延" in body["summary"]

    today_pending = (
        db.query(Task)
        .filter(Task.goal_id == goal["id"], Task.day == today, Task.status == "pending")
        .all()
    )
    assert [task.id for task in today_pending] == [highest["id"]]
    tomorrow_pending = (
        db.query(Task)
        .filter(
            Task.goal_id == goal["id"],
            Task.day == today + timedelta(days=1),
            Task.status == "pending",
        )
        .all()
    )
    assert len(tomorrow_pending) == 2
    assert all("疲劳降载" in task.reason for task in tomorrow_pending)
    assert all(today.isoformat() in task.reason for task in tomorrow_pending)

    log = db.query(ReplanLog).filter(ReplanLog.goal_id == goal["id"]).one()
    assert log.trigger == "rest"
    changes = json.loads(log.changes)
    assert changes[0]["kind"] == "rest"
    assert "顺延 2 个任务" in changes[0]["detail"]


def test_rest_with_single_pending_task_keeps_it(api, auth, goal, imported_points):
    token = auth["token"]
    tasks = _plan_today(api, token, goal["id"])
    for task in tasks[1:]:
        done = api("PATCH", f"/api/goals/tasks/{task['id']}", token=token, json={"status": "done"})
        assert done.status_code == 200, done.text

    response = api("POST", f"/api/goals/{goal['id']}/rest", token=token)

    assert response.status_code == 200
    body = response.json()
    assert body["moved"] == 0
    assert body["kept"] == 1
    assert body["summary"] == "今日任务已经足够精简，先把剩下的完成即可。"


def test_rest_skips_tasks_when_exam_is_tomorrow(api, auth, goal, imported_points, db):
    token = auth["token"]
    today = date.today()
    # 直接把考试日改到明天，今天即是可用的最后一天
    stored_goal = db.get(Goal, goal["id"])
    stored_goal.exam_date = today + timedelta(days=1)
    db.commit()

    tasks = _plan_today(api, token, goal["id"])
    assert len(tasks) == 3

    response = api("POST", f"/api/goals/{goal['id']}/rest", token=token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["moved"] == 0
    assert body["kept"] == 1
    assert "其余 0 个任务顺延" in body["summary"]


    db.expire_all()
    skipped = (
        db.query(Task)
        .filter(Task.goal_id == goal["id"], Task.status == "skipped", Task.day == today)
        .all()
    )
    assert len(skipped) == 2
    assert all("（疲劳降载，已取消）" in task.reason for task in skipped)


def test_rest_pushes_tasks_to_next_day_with_capacity(api, auth, goal, imported_points, db):
    token = auth["token"]
    today = date.today()

    stored_goal = db.get(Goal, goal["id"])
    stored_goal.daily_minutes = 60
    db.add(
        Task(
            user_id=auth["user"]["id"],
            goal_id=goal["id"],
            day=today + timedelta(days=1),
            title="次日已占用任务",
            type="study",
            duration_min=60,
            status="pending",
            reason="占满次日",
            priority=1.0,
            source="manual",
        )
    )
    db.commit()

    tasks = _plan_today(api, token, goal["id"])
    assert len(tasks) == 3

    response = api("POST", f"/api/goals/{goal['id']}/rest", token=token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kept"] == 1
    assert body["moved"] == 2

    db.expire_all()
    day_after = (
        db.query(Task)
        .filter(
            Task.goal_id == goal["id"],
            Task.day == today + timedelta(days=2),
            Task.status == "pending",
        )
        .all()
    )
    assert len(day_after) == 2
    assert all("（疲劳降载" in task.reason for task in day_after)
    tomorrow = (
        db.query(Task)
        .filter(Task.goal_id == goal["id"], Task.day == today + timedelta(days=1))
        .all()
    )
    assert len(tomorrow) == 1
    assert tomorrow[0].title == "次日已占用任务"


def test_rest_requires_authentication(api, goal):
    assert api("POST", f"/api/goals/{goal['id']}/rest").status_code == 401


def test_rest_rejects_unknown_goal(api, auth):
    response = api("POST", "/api/goals/99999/rest", token=auth["token"])
    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"