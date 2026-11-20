"""鸿蒙客户端所依赖的新接口：语音识别、多轮教练、学科包审核、教师工作台与教务对接。"""

import json

import pytest

from app.services.qa import is_followup, rule_answer_with_history


def _staff(api, username, role):
    response = api(
        "POST",
        "/api/auth/register",
        json={"username": username, "password": "secret123", "nickname": username, "role": role},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == role
    assert body["user"]["campus_access"] is True
    return body["access_token"]


def _package_body():
    return {
        "name": "课堂自编线性表",
        "subject": "计算机",
        "description": "教师整理的线性表课堂包",
        "tags": ["数据结构", "课堂"],
        "points": [
            {"name": "线性表", "parent": None, "weight": 1.5},
            {"name": "顺序表", "parent": "线性表", "weight": 1.2},
        ],
    }


def test_student_has_no_campus_access(auth):
    assert auth["user"]["role"] == "student"
    assert auth["user"]["campus_access"] is False


def test_asr_reports_not_configured_without_inventing_text(api, auth, monkeypatch):
    monkeypatch.setattr(
        "app.services.cloud_services.sis_audio_to_text",
        lambda *args, **kwargs: {
            "status": "not_configured",
            "detail": "未配置华为云凭证",
            "text": "",
        },
    )
    response = api(
        "POST",
        "/api/cloud/sis/recognize",
        token=auth["token"],
        files={"file": ("speech.wav", b"RIFFxxxx", "audio/wav")},
        data={"audio_format": "wav", "sample_rate": "16000"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "not_configured"
    assert body["text"] == ""
    assert body["fallback"] == "device_or_text"
    assert "本机" in body["fallback_label"]


def test_tts_without_audio_asks_for_device_speech(api, auth, monkeypatch):
    monkeypatch.setattr(
        "app.services.cloud_services.sis_text_to_audio",
        lambda *args, **kwargs: {"status": "not_configured", "detail": "未配置华为云凭证"},
    )
    response = api(
        "POST",
        "/api/cloud/sis/synthesize",
        token=auth["token"],
        data={"text": "今天先完成听力任务"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["audio_ready"] is False
    assert body["fallback"] == "device_speech"
    assert "audio_b64" not in body


def test_followup_reuses_previous_question(db, db_user_goal):
    user, goal = db_user_goal
    history = [{"role": "user", "text": "今天学什么"}, {"role": "coach", "text": "今天还没有排任务。"}]
    assert is_followup("为什么")
    result = rule_answer_with_history(db, user, goal, "为什么", history)
    assert result["followup"] is True
    assert "今天学什么" in result["answer"]
    assert "上一轮" in result["answer"]
    assert "还没完成" in result["answer"]


def test_coach_session_keeps_multiple_turns(api, auth, goal):
    created = api(
        "POST",
        "/api/coach/sessions",
        token=auth["token"],
        json={"goal_id": goal["id"], "title": "晚间答疑"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    first = api(
        "POST",
        f"/api/coach/sessions/{session_id}/messages",
        token=auth["token"],
        json={"text": "今天学什么", "goal_id": goal["id"]},
    )
    assert first.status_code == 200, first.text
    assert "今天" in first.json()["answer"]

    second = api(
        "POST",
        f"/api/coach/sessions/{session_id}/messages",
        token=auth["token"],
        json={"text": "为什么", "goal_id": goal["id"]},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["followup"] is True
    assert "今天学什么" in body["answer"]
    assert "上一轮" in body["answer"]
    assert len(body["messages"]) == 4
    assert [item["role"] for item in body["messages"]] == ["user", "coach", "user", "coach"]

    detail = api("GET", f"/api/coach/sessions/{session_id}", token=auth["token"])
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 4

    foreign = api("GET", f"/api/coach/sessions/{session_id}")
    assert foreign.status_code == 401


def test_voice_turn_does_not_invent_transcript(api, auth, monkeypatch):
    monkeypatch.setattr(
        "app.services.cloud_services.sis_audio_to_text",
        lambda *args, **kwargs: {"status": "sdk_missing", "detail": "未安装 SDK", "text": ""},
    )
    created = api("POST", "/api/coach/sessions", token=auth["token"], json={})
    session_id = created.json()["id"]
    response = api(
        "POST",
        f"/api/coach/sessions/{session_id}/voice",
        token=auth["token"],
        files={"file": ("speech.wav", b"RIFFxxxx", "audio/wav")},
        data={"audio_format": "wav"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "sdk_missing"
    assert body["text"] == ""
    assert body["fallback"] == "device_or_text"
    detail = api("GET", f"/api/coach/sessions/{session_id}", token=auth["token"]).json()
    assert detail["messages"] == []


def test_voice_stream_uses_rule_answer_when_model_absent(api, auth, goal):
    response = api(
        "POST",
        "/api/voice/ask/stream",
        token=auth["token"],
        json={"question": "今天学什么", "goal_id": goal["id"]},
    )
    assert response.status_code == 200
    assert "今天" in response.text


def test_custom_package_review_share_and_apply(api, auth, goal):
    teacher = _staff(api, "teacher1", "teacher")
    academic = _staff(api, "office1", "academic")

    denied = api("POST", "/api/skill-packages", token=auth["token"], json=_package_body())
    assert denied.status_code == 403

    created = api("POST", "/api/skill-packages", token=teacher, json=_package_body())
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]
    assert created.json()["status"] == "pending"

    listing = api("GET", "/api/skill-packages", token=auth["token"]).json()
    assert slug not in {item["slug"] for item in listing}

    blocked = api(
        "POST",
        f"/api/skill-packages/{slug}/apply",
        token=auth["token"],
        json={"goal_id": goal["id"]},
    )
    assert blocked.status_code == 400

    self_review = api(
        "POST",
        f"/api/skill-packages/{slug}/review",
        token=teacher,
        json={"action": "approve", "note": "自己审"},
    )
    assert self_review.status_code == 400

    approved = api(
        "POST",
        f"/api/skill-packages/{slug}/review",
        token=academic,
        json={"action": "approve", "note": "可以用于课堂"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["shared"] is False

    still_hidden = api("GET", "/api/skill-packages", token=auth["token"]).json()
    assert slug not in {item["slug"] for item in still_hidden}

    shared = api("POST", f"/api/skill-packages/{slug}/share", token=teacher)
    assert shared.status_code == 200, shared.text
    code = shared.json()["share_code"]
    assert code

    visible = api("GET", "/api/skill-packages", token=auth["token"]).json()
    assert slug in {item["slug"] for item in visible}

    applied = api(
        "POST",
        "/api/skill-packages/redeem",
        token=auth["token"],
        json={"share_code": code, "goal_id": goal["id"]},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["created"] == 2

    queue = api("GET", "/api/skill-packages/review", token=auth["token"])
    assert queue.status_code == 403


def test_reject_package_cannot_be_shared(api):
    teacher = _staff(api, "teacher2", "teacher")
    academic = _staff(api, "office2", "academic")
    created = api("POST", "/api/skill-packages", token=teacher, json=_package_body())
    slug = created.json()["slug"]
    rejected = api(
        "POST",
        f"/api/skill-packages/{slug}/review",
        token=academic,
        json={"action": "reject", "note": "知识点过少"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    share = api("POST", f"/api/skill-packages/{slug}/share", token=teacher)
    assert share.status_code == 400


def test_student_cannot_open_teacher_workbench(api, auth):
    response = api("GET", "/api/campus/workbench", token=auth["token"])
    assert response.status_code == 403


def test_workbench_compare_and_mock_bridge(api, monkeypatch):
    monkeypatch.delenv("ACADEMIC_BRIDGE_MODE", raising=False)
    monkeypatch.delenv("ACADEMIC_BRIDGE_URL", raising=False)
    monkeypatch.delenv("ACADEMIC_BRIDGE_TOKEN", raising=False)
    teacher = _staff(api, "teacher3", "teacher")

    status = api("GET", "/api/campus/bridge", token=teacher)
    assert status.status_code == 200
    assert status.json()["mode"] == "mock"
    assert "尚未配置" in status.json()["note"]

    synced = api("POST", "/api/campus/bridge/sync", token=teacher)
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert len(body["created"]) == 3
    assert "邀请码" in body["detail"] or "样例" in body["detail"]
    again = api("POST", "/api/campus/bridge/sync", token=teacher).json()
    assert again["created"] == []
    assert len(again["unchanged"]) == 3

    desk = api("GET", "/api/campus/workbench", token=teacher)
    assert desk.status_code == 200
    assert desk.json()["class_count"] == 3

    ids = ",".join(str(item["id"]) for item in body["created"][:2])
    compared = api("GET", "/api/campus/classes/compare", token=teacher, params={"ids": ids})
    assert compared.status_code == 200, compared.text
    report = compared.json()
    assert len(report["items"]) == 2
    assert report["items"][0]["member_count"] == 0
    assert report["items"][0]["basis"] == "sample"
    assert report["items"][0]["top_weak"] != report["items"][1]["top_weak"]
    assert report["items"][0]["completion_rate"] != report["items"][1]["completion_rate"]
    assert "样例对照" in report["summary"]
    assert "secret" not in compared.text

    pushed = api(
        "POST",
        "/api/campus/bridge/push",
        token=teacher,
        json={"class_id": body["created"][0]["id"]},
    )
    assert pushed.status_code == 200, pushed.text
    assert pushed.json()["status"] == "accepted"
    assert pushed.json()["mode"] == "mock"
    assert "没有发往外部系统" in pushed.json()["detail"]

    logs = api("GET", "/api/campus/bridge/logs", token=teacher)
    assert logs.status_code == 200
    assert len(logs.json()["items"]) >= 2


def test_http_bridge_hides_endpoint_and_token(api, monkeypatch):
    monkeypatch.setenv("ACADEMIC_BRIDGE_MODE", "http")
    monkeypatch.setenv("ACADEMIC_BRIDGE_URL", "http://secret.example/roster?token=abc")
    monkeypatch.setenv("ACADEMIC_BRIDGE_TOKEN", "super-secret-token")

    def explode(*args, **kwargs):
        raise OSError("timed out http://secret.example/roster?token=abc super-secret-token")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    teacher = _staff(api, "teacher4", "teacher")
    response = api("POST", "/api/campus/bridge/sync", token=teacher)
    assert response.status_code == 200
    text = response.text
    assert response.json()["status"] == "error"
    assert "secret.example" not in text
    assert "super-secret-token" not in text
    assert "abc" not in text


def test_enqueue_keeps_review_stage_and_makes_card_due(api, auth, goal, db):
    from app.models import KnowledgePoint, Mastery

    point = KnowledgePoint(goal_id=goal["id"], name="短对话", weight=1.2)
    db.add(point)
    db.commit()
    db.add(Mastery(user_id=auth["user"]["id"], kp_id=point.id, value=0.4, review_stage=2))
    db.commit()

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/enqueue",
        token=auth["token"],
        json={"kp_id": point.id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_stage"] == 2
    assert body["next_review_at"]
    assert "间隔没有被改写" in body["detail"]


def test_close_session_returns_at_most_three_points(api, auth, goal):
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
        json={"text": "今天学什么", "goal_id": goal["id"]},
    )
    api(
        "POST",
        f"/api/coach/sessions/{session_id}/messages",
        token=auth["token"],
        json={"text": "为什么", "goal_id": goal["id"]},
    )
    closed = api("POST", f"/api/coach/sessions/{session_id}/close", token=auth["token"])
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert 1 <= len(body["takeaways"]) <= 3
    assert body["next_practice"]
    empty = api("POST", "/api/coach/sessions", token=auth["token"], json={})
    denied = api("POST", f"/api/coach/sessions/{empty.json()['id']}/close", token=auth["token"])
    assert denied.status_code == 400


def test_dashboard_loop_and_week_activity(api, auth, goal):
    response = api("GET", "/api/dashboard", token=auth["token"], params={"goal_id": goal["id"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [step["key"] for step in body["loop_steps"]] == ["lesson", "quiz", "voice", "review"]
    assert body["loop_steps"][0]["done"] is False
    assert len(body["week_activity"]) == 7
    assert body["next_step"]


def test_teacher_can_assign_package_and_see_completion(api):
    teacher = _staff(api, "teacher6", "teacher")
    created = api(
        "POST",
        "/api/classes",
        token=teacher,
        json={"name": "英语提高班", "description": "课堂练习"},
    )
    assert created.status_code == 201, created.text
    class_id = created.json()["id"]
    assigned = api(
        "POST",
        f"/api/campus/classes/{class_id}/assignments",
        token=teacher,
        json={"slug": "cet4"},
    )
    assert assigned.status_code == 201, assigned.text
    body = assigned.json()
    assert body["title"] == "大学英语四级包"
    assert body["completion_rate"] == 0.0
    listed = api("GET", f"/api/campus/classes/{class_id}/assignments", token=teacher)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["slug"] == "cet4"


def test_http_bridge_imports_remote_roster(api, monkeypatch):
    monkeypatch.setenv("ACADEMIC_BRIDGE_MODE", "http")
    monkeypatch.setenv("ACADEMIC_BRIDGE_URL", "http://academic.internal/roster")
    monkeypatch.delenv("ACADEMIC_BRIDGE_TOKEN", raising=False)

    class _Body:
        def read(self, _limit=None):
            return json.dumps(
                [{"external_id": "remote-1", "name": "高数实验班", "department": "数学学院", "student_count": 30}]
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake_urlopen(request, timeout=8):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _Body()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    teacher = _staff(api, "teacher5", "teacher")
    response = api("POST", "/api/campus/bridge/sync", token=teacher)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "http"
    assert body["created"][0]["name"] == "高数实验班"
    assert seen["url"] == "http://academic.internal/roster"
    assert "academic.internal" not in response.text
