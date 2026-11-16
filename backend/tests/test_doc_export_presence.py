"""周报/错题本导出与摄像头在场结果落库的测试。"""

from datetime import date

from sqlalchemy import select

from app.models import EventLog, FocusSession, Report


def _seed_report(db, goal_id, user_id):
    db.add(
        Report(
            user_id=user_id,
            goal_id=goal_id,
            week_start=date(2026, 11, 2),
            week_end=date(2026, 11, 8),
            completion_rate=0.72,
            mastery_delta=0.05,
            focus="先补听力",
            content="本周完成率 72%。\n听力是最薄弱的一项。",
        )
    )
    db.commit()


def test_report_export_docx_has_ai_header(api, auth, goal, db):
    _seed_report(db, goal["id"], auth["user"]["id"])
    response = api("GET", f"/api/goals/{goal['id']}/reports/latest/export.docx", token=auth["token"])

    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # docx 是 zip 容器
    assert response.headers["X-AI-Generated"] == "true"
    assert "wordprocessingml" in response.headers["content-type"]


def test_report_export_pdf_has_ai_footer(api, auth, goal, db):
    _seed_report(db, goal["id"], auth["user"]["id"])
    response = api("GET", f"/api/goals/{goal['id']}/reports/latest/export.pdf", token=auth["token"])

    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"
    assert response.headers["X-AI-Generated"] == "true"
    assert response.headers["content-type"] == "application/pdf"


def test_mistakes_export_docx_contains_rows(api, auth, goal, db):
    created = api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes",
        token=auth["token"],
        json={
            "question": "He ____ here since 2020.",
            "user_answer": "lives",
            "correct_answer": "has lived",
        },
    )
    assert created.status_code == 201, created.text

    response = api("GET", f"/api/goals/{goal['id']}/mistakes/export.docx", token=auth["token"])

    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert len(response.content) > 5000


def test_focus_presence_records_result_not_image(api, auth, goal, db):
    started = api(
        "POST",
        "/api/focus/start",
        token=auth["token"],
        json={"goal_id": goal["id"], "planned_minutes": 25},
    )
    assert started.status_code == 200, started.text
    session_id = started.json()["id"]

    away = api(
        "POST",
        f"/api/focus/{session_id}/presence",
        token=auth["token"],
        json={"present": False, "luma": 3.2, "diff": 0.1, "note": "端侧判断：可能离开"},
    )
    assert away.status_code == 200
    body = away.json()
    assert body["recorded"] is True
    assert body["leaves"] >= 1
    assert body["snapshots"] >= 1

    back = api(
        "POST",
        f"/api/focus/{session_id}/presence",
        token=auth["token"],
        json={"present": True, "luma": 80.1, "diff": 12.0},
    )
    assert back.status_code == 200
    assert back.json()["leaves"] == body["leaves"]

    session = db.get(FocusSession, session_id)
    assert session.snapshots >= 2
    # 事件表里只记录判断结果，没有图片字段
    log = db.scalars(
        select(EventLog).where(EventLog.type == "focus_presence").order_by(EventLog.id.desc())
    ).first()
    assert log is not None
    assert log.handled_by
    assert "image" not in (log.payload or "")

    api("POST", f"/api/focus/{session_id}/abort", token=auth["token"], json={"reason": "测试结束"})
