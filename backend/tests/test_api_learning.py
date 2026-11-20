from datetime import date, datetime, timedelta

import pytest

import app.api.learning as learning_module
from app.models import Mistake, Task


def _plan(api, token, goal_id, days=2, regenerate=False):
    response = api(
        "POST",
        f"/api/goals/{goal_id}/plan",
        token=token,
        json={"days": days, "regenerate": regenerate},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_mistake_diagnoses_and_replans(api, auth, goal, imported_points):
    token = auth["token"]
    kp = imported_points[0]

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes",
        token=token,
        json={
            "question": "请计算该极限的值",
            "user_answer": "不会做",
            "correct_answer": "0",
            "kp_id": kp["id"],
            "source": "text",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["diagnosis"]["category"] == "method"
    assert body["diagnosis"]["category_label"] == "方法不会"
    assert body["diagnosis"]["engine"] == "rule"
    assert body["diagnosis"]["mastery"] == 0.08
    assert body["mistake"]["kp_name"] == kp["name"]
    assert body["replan"] is not None
    assert body["replan"]["changes"]


def test_create_mistake_can_skip_replan(api, auth, goal, imported_points):
    token = auth["token"]
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes?auto_replan=false",
        token=token,
        json={"question": "下列哪个选项正确", "user_answer": "", "correct_answer": "B"},
    )
    assert response.status_code == 201
    assert response.json()["replan"] is None
    assert response.json()["diagnosis"]["category"] == "time"


def test_create_mistake_rejects_unknown_knowledge_point(api, auth, goal):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes",
        token=auth["token"],
        json={"question": "题目", "user_answer": "答案", "correct_answer": "正确答案", "kp_id": 99999},
    )
    assert response.status_code == 400
    assert "知识点不存在" in response.json()["detail"]


def test_mistake_rate_limit(api, auth, goal, imported_points, monkeypatch):
    monkeypatch.setattr(learning_module.cache, "incr", lambda *args, **kwargs: 31)
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes",
        token=auth["token"],
        json={"question": "题目", "user_answer": "答案", "correct_answer": "正确答案"},
    )
    assert response.status_code == 429
    assert "频繁" in response.json()["detail"]


def test_list_and_delete_mistakes(api, auth, goal, imported_points):
    token = auth["token"]
    kp = imported_points[0]
    for _ in range(2):
        assert api(
            "POST",
            f"/api/goals/{goal['id']}/mistakes?auto_replan=false",
            token=token,
            json={
                "question": "请计算",
                "user_answer": "不会",
                "correct_answer": "0",
                "kp_id": kp["id"],
            },
        ).status_code == 201

    listed = api("GET", f"/api/goals/{goal['id']}/mistakes", token=token)
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    filtered = api("GET", f"/api/goals/{goal['id']}/mistakes?category=method", token=token)
    assert len(filtered.json()) == 2

    empty = api("GET", f"/api/goals/{goal['id']}/mistakes?category=careless", token=token)
    assert empty.json() == []

    mistake_id = listed.json()[0]["id"]
    assert api("DELETE", f"/api/goals/mistakes/{mistake_id}", token=token).status_code == 204
    assert api("DELETE", f"/api/goals/mistakes/{mistake_id}", token=token).status_code == 404

    other = api("POST", "/api/auth/register", json={"username": "other", "password": "secret123"})
    other_token = other.json()["access_token"]
    assert api("DELETE", f"/api/goals/mistakes/{listed.json()[1]['id']}", token=other_token).status_code == 404


def test_repeated_mistakes_insert_remedial_task(api, auth, goal, imported_points):
    token = auth["token"]
    kp = imported_points[0]
    payload = {
        "question": "请计算极限",
        "user_answer": "不会",
        "correct_answer": "0",
        "kp_id": kp["id"],
    }
    first = api("POST", f"/api/goals/{goal['id']}/mistakes", token=token, json=payload)
    assert first.status_code == 201
    first_tasks = [
        task for task in first.json()["replan"]["tasks"]
        if task["type"] == "remedial" and task["kp_id"] == kp["id"]
    ]
    assert len(first_tasks) == 1
    assert first_tasks[0]["duration_min"] == 20

    second = api("POST", f"/api/goals/{goal['id']}/mistakes", token=token, json=payload)
    assert second.status_code == 201
    second_tasks = [
        task for task in second.json()["replan"]["tasks"]
        if task["type"] == "remedial" and task["kp_id"] == kp["id"]
    ]
    assert len(second_tasks) == 1


def test_answer_updates_mastery(api, auth, goal, imported_points):
    token = auth["token"]
    kp = imported_points[0]

    correct = api(
        "POST",
        f"/api/goals/{goal['id']}/mastery/{kp['id']}/answer",
        token=token,
        json={"correct": True},
    )
    assert correct.status_code == 200
    body = correct.json()
    assert body["value"] == 0.08
    assert body["review_stage"] == 1
    assert body["next_review_at"] == (date.today() + timedelta(days=2)).isoformat()

    wrong = api(
        "POST",
        f"/api/goals/{goal['id']}/mastery/{kp['id']}/answer",
        token=token,
        json={"correct": False},
    )
    assert wrong.status_code == 200
    assert wrong.json()["value"] == 0.0957
    assert wrong.json()["review_stage"] == 0

    missing = api(
        "POST",
        f"/api/goals/{goal['id']}/mastery/99999/answer",
        token=token,
        json={"correct": True},
    )
    assert missing.status_code == 404


def test_mastery_of_another_goal_is_rejected(api, auth, goal, imported_points):
    token = auth["token"]
    second = api(
        "POST",
        "/api/goals",
        token=token,
        json={
            "exam_name": "HCIA",
            "exam_date": (date.today() + timedelta(days=30)).isoformat(),
            "daily_minutes": 60,
        },
    )
    other_goal = second.json()
    point = api(
        "POST",
        f"/api/goals/{other_goal['id']}/knowledge-points",
        token=token,
        json={"name": "网络基础", "weight": 1.0},
    )
    assert point.status_code == 201

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/mastery/{point.json()['id']}/answer",
        token=token,
        json={"correct": True},
    )
    assert response.status_code == 404


def test_list_mastery_includes_delta(api, auth, goal, imported_points):
    token = auth["token"]
    kp = imported_points[0]
    api("POST", f"/api/goals/{goal['id']}/mastery/{kp['id']}/answer", token=token, json={"correct": True})

    listed = api("GET", f"/api/goals/{goal['id']}/mastery", token=token)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == len(imported_points)
    target = next(row for row in rows if row["kp_id"] == kp["id"])
    assert target["value"] == 0.08
    assert target["delta_7d"] == 0.0
    weights = [row["kp_name"] for row in rows]
    assert weights


def test_generate_and_list_reports(api, auth, goal, imported_points):
    token = auth["token"]
    created = api("POST", f"/api/goals/{goal['id']}/reports", token=token)
    assert created.status_code == 200
    report = created.json()
    assert report["completion_rate"] == 0.0
    assert "【本周概览】" in report["content"]

    listed = api("GET", f"/api/goals/{goal['id']}/reports", token=token)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == report["id"]

    latest = api("GET", f"/api/goals/{goal['id']}/reports/latest", token=token)
    assert latest.json()["id"] == report["id"]


def test_latest_report_is_null_without_reports(api, auth, goal):
    response = api("GET", f"/api/goals/{goal['id']}/reports/latest", token=auth["token"])
    assert response.status_code == 200
    assert response.json() is None


def test_generate_plan_and_list_tasks(api, auth, goal, imported_points):
    token = auth["token"]
    result = _plan(api, token, goal["id"], days=3)
    assert result["days"] == 3
    assert len(result["tasks"]) == 9
    assert result["total_minutes"] == 3 * 90
    assert "微任务" in result["summary"]

    tasks = api("GET", f"/api/goals/{goal['id']}/tasks", token=token)
    assert tasks.status_code == 200
    assert len(tasks.json()) == 9

    first_day = tasks.json()[0]["day"]
    filtered = api(
        "GET",
        f"/api/goals/{goal['id']}/tasks",
        token=token,
        params={"start": first_day, "end": first_day},
    )
    assert len(filtered.json()) == 3


def test_regenerate_plan_replaces_pending_tasks(api, auth, goal, imported_points, db):
    token = auth["token"]
    _plan(api, token, goal["id"], days=2)

    result = _plan(api, token, goal["id"], days=2, regenerate=True)
    assert len(result["tasks"]) == 6
    second_ids = {task.id for task in db.query(Task).all()}
    assert len(second_ids) == 6
    # 重新生成不允许出现重复任务行
    assert all(task.status == "pending" for task in db.query(Task).all())


def test_update_task_status(api, auth, goal, imported_points):
    token = auth["token"]
    plan = _plan(api, token, goal["id"], days=1)
    task_id = plan["tasks"][0]["id"]

    done = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"

    reopened = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "pending"})
    assert reopened.json()["status"] == "pending"

    invalid = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "bogus"})
    assert invalid.status_code == 422

    missing = api("PATCH", "/api/goals/tasks/99999", token=token, json={"status": "done"})
    assert missing.status_code == 404


def test_replan_endpoint_and_logs(api, auth, goal, imported_points):
    token = auth["token"]
    _plan(api, token, goal["id"], days=2)

    response = api("POST", f"/api/goals/{goal['id']}/replan?trigger=manual", token=token)
    assert response.status_code == 200
    assert response.json()["trigger"] == "manual"
    assert response.json()["changes"]

    logs = api("GET", f"/api/goals/{goal['id']}/replan-logs", token=token)
    assert logs.status_code == 200
    assert logs.json()[0]["trigger"] == "manual"
    assert isinstance(logs.json()[0]["changes"], list)


def test_replan_logs_limit_validation(api, auth, goal):
    response = api("GET", f"/api/goals/{goal['id']}/replan-logs?limit=99", token=auth["token"])
    assert response.status_code == 422


def test_mistakes_are_scoped_to_goal(api, auth, goal):
    other = api("POST", "/api/auth/register", json={"username": "other", "password": "secret123"})
    assert other.status_code == 201
    other_token = other.json()["access_token"]
    assert api("GET", f"/api/goals/{goal['id']}/mistakes", token=other_token).status_code == 404

def _force_goal(api, token, goal, **overrides):
    payload = {
        "exam_name": goal["exam_name"],
        "exam_date": goal["exam_date"],
        "daily_minutes": goal["daily_minutes"],
        "force_mode": True,
        "min_daily_minutes": goal.get("min_daily_minutes", 30),
        "camera_required": goal.get("camera_required", False),
    }
    payload.update(overrides)
    response = api("PUT", f"/api/goals/{goal['id']}", token=token, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_force_mode_blocks_skipping_task(api, auth, goal, imported_points):
    token = auth["token"]
    assert _force_goal(api, token, goal)["force_mode"] is True
    task_id = _plan(api, token, goal["id"], days=1)["tasks"][0]["id"]

    response = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "skipped"})

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "强制学习模式已开启：任务不能跳过，请进入「强制学习」完成或中止并记录违约"
    )
    tasks = api("GET", f"/api/goals/{goal['id']}/tasks", token=token).json()
    assert next(task for task in tasks if task["id"] == task_id)["status"] == "pending"


def test_force_mode_allows_done_and_reopen(api, auth, goal, imported_points):
    token = auth["token"]
    _force_goal(api, token, goal)
    task_id = _plan(api, token, goal["id"], days=1)["tasks"][0]["id"]

    done = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "done"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"

    reopened = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "pending"})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "pending"


def test_skip_is_allowed_without_force_mode(api, auth, goal, imported_points):
    token = auth["token"]
    task_id = _plan(api, token, goal["id"], days=1)["tasks"][0]["id"]

    response = api("PATCH", f"/api/goals/tasks/{task_id}", token=token, json={"status": "skipped"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "skipped"


def test_task_status_is_scoped_to_owner(api, auth, goal, imported_points):
    token = auth["token"]
    task_id = _plan(api, token, goal["id"], days=1)["tasks"][0]["id"]
    other = api("POST", "/api/auth/register", json={"username": "other2", "password": "secret123"})
    assert other.status_code == 201, other.text

    response = api(
        "PATCH",
        f"/api/goals/tasks/{task_id}",
        token=other.json()["access_token"],
        json={"status": "done"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


def test_auto_adjust_endpoint_generates_today_plan_once(api, auth, goal, imported_points):
    token = auth["token"]

    first = api("POST", f"/api/goals/{goal['id']}/auto-adjust", token=token)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["adjusted"] is True
    assert body["summary"] == "今天还没有任务，已根据剩余时间自动生成今日计划。"
    assert body["changes"][0]["kind"] == "auto_plan"
    assert body["days_left"] == 40
    assert body["force_mode"] is False
    assert body["sprint_mode"] is False
    assert body["mandatory_remaining"] >= 1

    second = api("POST", f"/api/goals/{goal['id']}/auto-adjust", token=token)
    assert second.status_code == 200, second.text
    assert second.json()["adjusted"] is False
    assert second.json()["mandatory_remaining"] == body["mandatory_remaining"]


def test_auto_adjust_endpoint_rejects_foreign_goal(api, goal):
    other = api("POST", "/api/auth/register", json={"username": "other3", "password": "secret123"})
    assert other.status_code == 201, other.text

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/auto-adjust",
        token=other.json()["access_token"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"


def test_replan_logs_tolerate_broken_changes_json(api, auth, goal, db):
    from app.models import ReplanLog

    db.add(
        ReplanLog(
            user_id=auth["user"]["id"],
            goal_id=goal["id"],
            trigger="manual",
            changes="{broken json",
        )
    )
    db.commit()

    response = api("GET", f"/api/goals/{goal['id']}/replan-logs", token=auth["token"])

    assert response.status_code == 200, response.text
    assert response.json()[0]["trigger"] == "manual"
    assert response.json()[0]["changes"] == []
