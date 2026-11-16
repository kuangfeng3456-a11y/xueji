"""强制学习与摄像头见证接口测试（app/api/focus.py）。

覆盖：开始/复用专注会话、摄像头要求继承、任务校验、离开次数中止、
学习见证上传校验、完成/中止与违约记录、到期自动完成、历史与权限隔离。
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from app.config import settings
from app.models import FocusSession, Task

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5a0000000049454e44ae426082"
)


def _add_task(
    db,
    user_id,
    goal_id,
    *,
    day=None,
    status="pending",
    title="听力练习",
    type_="study",
):
    task = Task(
        user_id=user_id,
        goal_id=goal_id,
        day=day or date.today(),
        title=title,
        type=type_,
        duration_min=20,
        status=status,
        priority=1.0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _start(api, token, goal_id, **overrides):
    payload = {"goal_id": goal_id, "planned_minutes": 5}
    payload.update(overrides)
    response = api("POST", "/api/focus/start", token=token, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _goal_payload(goal, **overrides):
    payload = {
        "exam_name": goal["exam_name"],
        "exam_date": goal["exam_date"],
        "daily_minutes": goal["daily_minutes"],
        "force_mode": goal.get("force_mode", False),
        "min_daily_minutes": goal.get("min_daily_minutes", 30),
        "camera_required": goal.get("camera_required", False),
    }
    payload.update(overrides)
    return payload


def test_start_focus_creates_active_session(api, auth, goal):
    body = _start(api, auth["token"], goal["id"], planned_minutes=5)

    assert body["status"] == "active"
    assert body["goal_id"] == goal["id"]
    assert body["planned_minutes"] == 5
    assert body["actual_minutes"] == 0
    assert body["camera_enabled"] is False
    assert body["leaves"] == 0
    assert body["snapshots"] == 0
    assert body["ended_at"] is None
    assert body["unlocked"] is False
    assert 0 < body["remaining_seconds"] <= 300


def test_start_focus_reuses_existing_active_session(api, auth, goal):
    first = _start(api, auth["token"], goal["id"])

    second = api(
        "POST",
        "/api/focus/start",
        token=auth["token"],
        json={"goal_id": goal["id"], "planned_minutes": 30, "camera_enabled": True},
    )

    assert second.status_code == 200, second.text
    assert second.json()["id"] == first["id"]
    assert second.json()["planned_minutes"] == 5


def test_start_focus_honours_goal_camera_requirement(api, auth, goal):
    updated = api(
        "PUT",
        f"/api/goals/{goal['id']}",
        token=auth["token"],
        json=_goal_payload(goal, camera_required=True),
    )
    assert updated.status_code == 200, updated.text

    inherited = _start(api, auth["token"], goal["id"], camera_enabled=False)
    assert inherited["camera_enabled"] is True


def test_start_focus_allows_payload_camera_without_goal_requirement(api, auth, goal):
    assert goal["camera_required"] is False

    body = _start(api, auth["token"], goal["id"], camera_enabled=True)

    assert body["camera_enabled"] is True


def test_start_focus_rejects_unknown_task(api, auth, goal):
    response = api(
        "POST",
        "/api/focus/start",
        token=auth["token"],
        json={"goal_id": goal["id"], "task_id": 99999, "planned_minutes": 10},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


def test_start_focus_rejects_task_from_other_goal(api, auth, goal, db):
    other = api(
        "POST",
        "/api/goals",
        token=auth["token"],
        json={
            "exam_name": "考研数学",
            "exam_date": goal["exam_date"],
            "daily_minutes": 60,
        },
    )
    assert other.status_code == 201, other.text
    foreign_task = _add_task(db, auth["user"]["id"], other.json()["id"], title="外置任务")

    response = api(
        "POST",
        "/api/focus/start",
        token=auth["token"],
        json={"goal_id": goal["id"], "task_id": foreign_task.id, "planned_minutes": 10},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


def test_start_focus_rejects_finished_task(api, auth, goal, db):
    task = _add_task(db, auth["user"]["id"], goal["id"], status="done")

    response = api(
        "POST",
        "/api/focus/start",
        token=auth["token"],
        json={"goal_id": goal["id"], "task_id": task.id, "planned_minutes": 10},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "该任务已经完成"


def test_heartbeat_aborts_after_three_leaves(api, auth, goal):
    session = _start(api, auth["token"], goal["id"])

    warned = api(
        "POST", f"/api/focus/{session['id']}/heartbeat", token=auth["token"], json={"leaves": 2}
    )
    assert warned.status_code == 200, warned.text
    assert warned.json()["status"] == "active"
    assert warned.json()["leaves"] == 2

    aborted = api(
        "POST", f"/api/focus/{session['id']}/heartbeat", token=auth["token"], json={"leaves": 3}
    )
    assert aborted.status_code == 200, aborted.text
    body = aborted.json()
    assert body["status"] == "aborted"
    assert body["leaves"] == 3
    assert body["note"] == "离开专注页面 3 次，自动中止"
    assert body["ended_at"] is not None
    assert body["remaining_seconds"] == 0

    again = api(
        "POST", f"/api/focus/{session['id']}/heartbeat", token=auth["token"], json={"leaves": 9}
    )
    assert again.json()["status"] == "aborted"
    assert again.json()["leaves"] == 3

    violations = api("GET", f"/api/goals/{goal['id']}/violations", token=auth["token"])
    assert violations.status_code == 200, violations.text
    rows = violations.json()
    assert len(rows) == 1
    assert rows[0]["kind"] == "leave"
    assert rows[0]["detail"] == "离开专注页面 3 次，自动中止"


def test_finish_focus_marks_task_done_and_unlocks(api, auth, goal, db):
    task = _add_task(db, auth["user"]["id"], goal["id"])
    session = _start(api, auth["token"], goal["id"], task_id=task.id, planned_minutes=10)

    finished = api(
        "POST",
        f"/api/focus/{session['id']}/finish",
        token=auth["token"],
        json={"actual_minutes": 8, "note": "完成听力训练"},
    )

    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "completed"
    assert body["actual_minutes"] == 8
    assert body["note"] == "完成听力训练"
    assert body["task_id"] == task.id
    assert body["task_title"] == "听力练习"
    assert body["unlocked"] is True
    assert body["ended_at"] is not None

    db.expire_all()
    assert db.get(Task, task.id).status == "done"
    assert db.get(Task, task.id).done_at is not None


def test_finish_focus_short_session_records_violation(api, auth, goal, db):
    task = _add_task(db, auth["user"]["id"], goal["id"])
    session = _start(api, auth["token"], goal["id"], task_id=task.id, planned_minutes=10)

    finished = api(
        "POST",
        f"/api/focus/{session['id']}/finish",
        token=auth["token"],
        json={"actual_minutes": 3, "note": "只学了 3 分钟"},
    )

    body = finished.json()
    assert body["status"] == "aborted"
    assert body["actual_minutes"] == 3
    assert body["unlocked"] is False

    db.expire_all()
    assert db.get(Task, task.id).status == "pending"

    violations = api("GET", f"/api/goals/{goal['id']}/violations", token=auth["token"]).json()
    assert [row["kind"] for row in violations] == ["short"]
    assert violations[0]["detail"] == "计划专注 10 分钟，实际只完成 3 分钟"


def test_finish_focus_defaults_actual_minutes_to_elapsed(api, auth, goal):
    session = _start(api, auth["token"], goal["id"], planned_minutes=5)

    finished = api(
        "POST",
        f"/api/focus/{session['id']}/finish",
        token=auth["token"],
        json={"note": "没填实际时长"},
    )

    body = finished.json()
    assert body["actual_minutes"] == 1
    assert body["status"] == "aborted"
    assert body["note"] == "没填实际时长"
    violations = api("GET", f"/api/goals/{goal['id']}/violations", token=auth["token"]).json()
    assert violations[0]["detail"] == "计划专注 5 分钟，实际只完成 1 分钟"


def test_abort_focus_records_reason_and_violation(api, auth, goal):
    session = _start(api, auth["token"], goal["id"], planned_minutes=10)

    aborted = api(
        "POST",
        f"/api/focus/{session['id']}/abort",
        token=auth["token"],
        json={"reason": "临时有事离开"},
    )

    assert aborted.status_code == 200, aborted.text
    body = aborted.json()
    assert body["status"] == "aborted"
    assert body["note"] == "临时有事离开"
    assert body["actual_minutes"] == 0
    assert body["remaining_seconds"] == 0

    again = api(
        "POST",
        f"/api/focus/{session['id']}/abort",
        token=auth["token"],
        json={"reason": "重复中止"},
    )
    assert again.json()["note"] == "临时有事离开"

    violations = api("GET", f"/api/goals/{goal['id']}/violations", token=auth["token"]).json()
    assert len(violations) == 1
    assert violations[0]["kind"] == "abort"
    assert violations[0]["detail"] == "临时有事离开"


def test_snapshot_upload_validates_type_and_size(api, auth, goal, monkeypatch):
    session = _start(api, auth["token"], goal["id"])

    bad_type = api(
        "POST",
        f"/api/focus/{session['id']}/snapshot",
        token=auth["token"],
        files={"file": ("focus.gif", b"GIF89a", "image/gif")},
    )
    assert bad_type.status_code == 400
    assert bad_type.json()["detail"] == "仅支持 jpg / png / webp"

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 4)
    too_large = api(
        "POST",
        f"/api/focus/{session['id']}/snapshot",
        token=auth["token"],
        files={"file": ("focus.png", PNG, "image/png")},
    )
    assert too_large.status_code == 400
    assert too_large.json()["detail"] == "图片超过 5MB"


def test_snapshot_upload_persists_file(api, auth, goal):
    session = _start(api, auth["token"], goal["id"])

    response = api(
        "POST",
        f"/api/focus/{session['id']}/snapshot",
        token=auth["token"],
        files={"file": ("focus.png", PNG, "image/png")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["snapshots"] == 1
    assert body["url"].startswith(f"/uploads/{auth['user']['id']}/")
    assert body["url"].endswith(".png")

    relative = body["url"][len("/uploads/"):]
    stored = Path(settings.UPLOAD_DIR) / relative
    try:
        assert stored.exists()
        assert stored.read_bytes() == PNG
    finally:
        stored.unlink(missing_ok=True)

    webp = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16
    second = api(
        "POST",
        f"/api/focus/{session['id']}/snapshot",
        token=auth["token"],
        files={"file": ("focus.webp", webp, "image/webp")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["snapshots"] == 2
    assert second.json()["url"].endswith(".webp")
    Path(settings.UPLOAD_DIR, second.json()["url"][len("/uploads/"):]).unlink(missing_ok=True)


def test_snapshot_rejected_after_session_ended(api, auth, goal):
    session = _start(api, auth["token"], goal["id"])
    api("POST", f"/api/focus/{session['id']}/abort", token=auth["token"], json={"reason": "结束"})

    response = api(
        "POST",
        f"/api/focus/{session['id']}/snapshot",
        token=auth["token"],
        files={"file": ("focus.png", PNG, "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "专注已结束，无法上传学习见证"


def test_active_focus_auto_completes_when_time_runs_out(api, auth, goal, db):
    task = _add_task(db, auth["user"]["id"], goal["id"])
    session = _start(api, auth["token"], goal["id"], task_id=task.id, planned_minutes=5)

    record = db.get(FocusSession, session["id"])
    record.started_at = datetime.utcnow() - timedelta(minutes=10)
    db.commit()

    active = api(
        "GET", "/api/focus/active", token=auth["token"], params={"goal_id": goal["id"]}
    )

    assert active.status_code == 200, active.text
    body = active.json()
    assert body["status"] == "completed"
    assert body["actual_minutes"] == 5
    assert body["remaining_seconds"] == 0
    assert body["ended_at"] is not None
    assert body["unlocked"] is True

    db.expire_all()
    assert db.get(Task, task.id).status == "done"


def test_active_focus_returns_null_without_session(api, auth, goal):
    active = api("GET", "/api/focus/active", token=auth["token"], params={"goal_id": goal["id"]})

    assert active.status_code == 200
    assert active.json() is None


def test_focus_history_and_limit(api, auth, goal):
    session = _start(api, auth["token"], goal["id"])
    api("POST", f"/api/focus/{session['id']}/abort", token=auth["token"], json={"reason": "结束"})

    history = api("GET", "/api/focus/history", token=auth["token"], params={"goal_id": goal["id"]})
    assert history.status_code == 200, history.text
    assert len(history.json()) == 1
    assert history.json()[0]["id"] == session["id"]

    invalid = api(
        "GET", "/api/focus/history", token=auth["token"], params={"goal_id": goal["id"], "limit": 0}
    )
    assert invalid.status_code == 422


def test_focus_endpoints_require_authentication_and_goal_ownership(api, goal, auth):
    unauthenticated = api("GET", "/api/focus/active")
    assert unauthenticated.status_code == 401

    intruder = api(
        "POST",
        "/api/auth/register",
        json={"username": "intruder", "password": "secret123", "nickname": "入侵者"},
    )
    assert intruder.status_code == 201, intruder.text
    intruder_token = intruder.json()["access_token"]

    foreign_start = api(
        "POST",
        "/api/focus/start",
        token=intruder_token,
        json={"goal_id": goal["id"], "planned_minutes": 10},
    )
    assert foreign_start.status_code == 404
    assert foreign_start.json()["detail"] == "目标不存在"

    session = _start(api, auth["token"], goal["id"])
    foreign_heartbeat = api(
        "POST",
        f"/api/focus/{session['id']}/heartbeat",
        token=intruder_token,
        json={"leaves": 1},
    )
    assert foreign_heartbeat.status_code == 404
    assert foreign_heartbeat.json()["detail"] == "专注记录不存在"

    missing = api(
        "POST", "/api/focus/99999/heartbeat", token=auth["token"], json={"leaves": 1}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "专注记录不存在"




def test_finish_focus_is_idempotent_after_session_ended(api, auth, goal):
    session = _start(api, auth["token"], goal["id"], planned_minutes=5)
    first = api(
        "POST",
        f"/api/focus/{session['id']}/finish",
        token=auth["token"],
        json={"actual_minutes": 8, "note": "第一次完成"},
    )
    assert first.json()["status"] == "completed"
    assert first.json()["actual_minutes"] == 8

    again = api(
        "POST",
        f"/api/focus/{session['id']}/finish",
        token=auth["token"],
        json={"actual_minutes": 60, "note": "重复提交"},
    )

    assert again.status_code == 200
    assert again.json()["status"] == "completed"
    assert again.json()["actual_minutes"] == 8
    assert again.json()["note"] == "第一次完成"


def test_focus_summary_is_full_scope_beyond_history_limit(api, auth, goal, db):
    """历史列表默认只回 10 条，累计时长/次数必须用全量聚合，否则会被截断。"""
    token = auth["token"]
    for _ in range(12):
        session = _start(api, token, goal["id"])
        api("POST", f"/api/focus/{session['id']}/finish", token=token, json={"note": ""})

    db.expire_all()
    for record in db.query(FocusSession).all():
        record.actual_minutes = 5
        record.status = "completed"
    db.commit()

    history = api("GET", "/api/focus/history", token=token, params={"goal_id": goal["id"]}).json()
    assert len(history) == 10, "历史列表默认上限 10 条"

    summary = api(
        "GET", f"/api/goals/{goal['id']}/focus/summary", token=token
    ).json()
    assert summary["sessions"] == 12
    assert summary["total_minutes"] == 60
    assert summary["avg_minutes"] == 5.0
    assert summary["violations"] >= 0
