"""答错、复习和教师布置会改变今天剩下的任务与下一步。"""

from datetime import date, timedelta

from app.models import KnowledgePoint, Mastery


def _point(db, user_id, goal_id, name, value):
    point = KnowledgePoint(goal_id=goal_id, name=name, weight=1.4)
    db.add(point)
    db.commit()
    db.add(Mastery(user_id=user_id, kp_id=point.id, value=value, review_stage=1))
    db.commit()
    return point


def test_wrong_answer_changes_today_and_next_step(api, auth, goal, db):
    point = _point(db, auth["user"]["id"], goal["id"], "短对话", 0.2)
    other = api(
        "POST",
        "/api/auth/register",
        json={"username": "steady", "password": "secret123", "nickname": "稳妥"},
    )
    assert other.status_code == 201, other.text
    other_token = other.json()["access_token"]
    other_goal = api(
        "POST",
        "/api/goals",
        token=other_token,
        json={
            "exam_name": "大学英语四级",
            "exam_date": (date.today() + timedelta(days=40)).isoformat(),
            "daily_minutes": 90,
        },
    ).json()
    _point(db, other.json()["user"]["id"], other_goal["id"], "短对话", 0.8)

    mistake = api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes",
        token=auth["token"],
        json={"question": "短对话里说话人的态度是什么？", "kp_id": point.id, "source": "text"},
    )
    assert mistake.status_code == 201, mistake.text

    weak = api("GET", "/api/dashboard", token=auth["token"], params={"goal_id": goal["id"]}).json()
    steady = api("GET", "/api/dashboard", token=other_token, params={"goal_id": other_goal["id"]}).json()
    weak_titles = [item["title"] for item in weak["today_tasks"]]
    steady_titles = [item["title"] for item in steady["today_tasks"]]
    assert any("短对话" in title for title in weak_titles)
    assert not any("针对弱项：短对话" in title for title in steady_titles)
    assert "短对话" in weak["next_step"]
    assert weak["next_step"] != steady["next_step"]
    assert "短对话" in weak["today_digest"]["still_weak"]


def test_remembered_review_leaves_practice_queue(api, auth, goal, db):
    point = _point(db, auth["user"]["id"], goal["id"], "长对话", 0.8)
    queued = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/enqueue",
        token=auth["token"],
        json={"kp_id": point.id},
    )
    assert queued.status_code == 200, queued.text
    before = api("GET", f"/api/goals/{goal['id']}/tasks", token=auth["token"]).json()
    assert any(item["title"] == "针对弱项：长对话" and item["status"] == "pending" for item in before)

    reviewed = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/{point.id}/review",
        token=auth["token"],
        json={"remembered": True},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["mastery"] >= 0.5
    after = api("GET", f"/api/goals/{goal['id']}/tasks", token=auth["token"]).json()
    matched = [item for item in after if item["title"] == "针对弱项：长对话"]
    assert matched and matched[0]["status"] == "done"


def test_forgotten_review_keeps_a_practice_task(api, auth, goal, db):
    point = _point(db, auth["user"]["id"], goal["id"], "听力篇章", 0.35)
    reviewed = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/{point.id}/review",
        token=auth["token"],
        json={"remembered": False},
    )
    assert reviewed.status_code == 200, reviewed.text
    tasks = api("GET", f"/api/goals/{goal['id']}/tasks", token=auth["token"]).json()
    assert any(item["kp_id"] == point.id and item["status"] == "pending" for item in tasks)


def test_assignment_appears_for_student_and_counts_when_done(api, auth, goal):
    teacher = api(
        "POST",
        "/api/auth/register",
        json={"username": "teacher9", "password": "secret123", "nickname": "教师", "role": "teacher"},
    )
    assert teacher.status_code == 201, teacher.text
    token = teacher.json()["access_token"]
    classroom = api(
        "POST",
        "/api/classes",
        token=token,
        json={"name": "英语一班", "description": "布置练习"},
    ).json()
    assigned = api(
        "POST",
        f"/api/campus/classes/{classroom['id']}/assignments",
        token=token,
        json={"slug": "cet4"},
    )
    assert assigned.status_code == 201, assigned.text
    joined = api(
        "POST",
        "/api/classes/join",
        token=auth["token"],
        json={"invite_code": classroom["invite_code"]},
    )
    assert joined.status_code == 200, joined.text

    board = api("GET", "/api/dashboard", token=auth["token"], params={"goal_id": goal["id"]}).json()
    task = next(item for item in board["today_tasks"] if item["title"].startswith("教师布置"))
    assert board["assignments"]
    done = api(
        "PATCH",
        f"/api/goals/tasks/{task['id']}",
        token=auth["token"],
        json={"status": "done"},
    )
    assert done.status_code == 200, done.text
    progress = api(
        "GET",
        f"/api/campus/classes/{classroom['id']}/assignments",
        token=token,
    ).json()
    assert progress["items"][0]["finished"] >= 1
    assert progress["items"][0]["completion_rate"] > 0


def test_coach_close_steers_named_weak_point(api, auth, goal, db):
    _point(db, auth["user"]["id"], goal["id"], "仔细阅读", 0.25)
    created = api(
        "POST",
        "/api/coach/sessions",
        token=auth["token"],
        json={"goal_id": goal["id"]},
    )
    session_id = created.json()["id"]
    api(
        "POST",
        f"/api/coach/sessions/{session_id}/messages",
        token=auth["token"],
        json={"text": "仔细阅读总是做错，下一步怎么练？", "goal_id": goal["id"]},
    )
    closed = api("POST", f"/api/coach/sessions/{session_id}/close", token=auth["token"])
    assert closed.status_code == 200, closed.text
    assert "仔细阅读" in closed.json()["next_practice"]
    tasks = api("GET", f"/api/goals/{goal['id']}/tasks", token=auth["token"]).json()
    assert any("仔细阅读" in item["title"] and item["status"] == "pending" for item in tasks)
