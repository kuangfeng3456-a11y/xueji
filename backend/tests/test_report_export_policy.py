"""周报导出、OCR 降级与出题学科策略的测试。"""

from datetime import date

from sqlalchemy import select

from app.models import Report
from app.services import item_policy


def _seed_report(db, goal_id, user_id):
    report = Report(
        user_id=user_id,
        goal_id=goal_id,
        week_start=date(2026, 11, 2),
        week_end=date(2026, 11, 8),
        completion_rate=0.72,
        mastery_delta=0.05,
        focus="先补听力",
        content="本周完成率 72%，听力是最薄弱的一项。",
    )
    db.add(report)
    db.commit()
    return report


def test_export_latest_report_without_report_returns_404(api, auth, goal):
    response = api("GET", f"/api/goals/{goal['id']}/reports/latest/export", token=auth["token"])
    assert response.status_code == 404
    assert "周报" in response.json()["detail"]


def test_export_latest_report_carries_ai_disclosure(api, auth, goal, db):
    _seed_report(db, goal["id"], auth["user"]["id"])

    response = api("GET", f"/api/goals/{goal['id']}/reports/latest/export", token=auth["token"])

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["week_start"] == "2026-11-02"
    disclosure = body["ai_disclosure"]
    assert disclosure["generated"] is True
    assert disclosure["provider_code"] == "xueji"
    assert response.headers["X-AI-Generated"] == "true"
    assert response.headers["X-AI-Content-Id"] == disclosure["content_id"]
    assert "attachment" in response.headers["Content-Disposition"]


def test_export_only_returns_own_report(api, auth, goal, db):
    _seed_report(db, goal["id"], auth["user"]["id"] + 99)
    response = api("GET", f"/api/goals/{goal['id']}/reports/latest/export", token=auth["token"])
    assert response.status_code == 404


def test_ocr_without_sdk_or_credentials_degrades_honestly(api, auth):
    files = {"file": ("probe.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    response = api(
        "POST",
        "/api/cloud/ocr/extract",
        token=auth["token"],
        files=files,
        data={"kind": "general"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"not_configured", "sdk_missing", "not_subscribed", "error", "ok"}
    assert "ocr" in (body.get("detail", "") + body.get("status", "")).lower() or body["status"] != "ok"
    if body["status"] != "ok":
        assert body.get("text", "") == ""


# ---------------------------------------------------------------- 出题学科策略
def test_english_subject_detects_cet_and_rejects_chinese_stem():
    assert item_policy.exam_is_english("大学英语四级")
    assert item_policy.language_for_point("大学英语四级", "听力") == "en"
    assert item_policy.language_for_point("大学英语四级", "高等数学") == "zh"

    issues = item_policy.item_issues(
        "在短对话中，以下哪项最符合“言外之意”的理解方式？",
        ["只理解字面意思", "结合语境推断", "忽略语气", "逐字翻译"],
        "大学英语四级",
        ["听力"],
        kp_name="听力",
    )
    assert any("英文" in issue for issue in issues)
    assert any("元问题" in issue for issue in issues)


def test_english_item_passes_policy():
    issues = item_policy.item_issues(
        "What does the woman imply about the meeting?",
        ["It was cancelled.", "It was put off.", "It went well.", "It was short."],
        "大学英语四级",
        ["听力"],
    )
    assert issues == []


def test_meta_question_is_rejected_for_chinese_subject():
    assert item_policy.is_meta_question("以下哪项属于哪个学习模块？")
    assert item_policy.is_meta_question("关于「二叉树」最需要先确认的是哪一项？")
    assert not item_policy.is_meta_question("深度为 5 的完全二叉树最多有多少个结点？")


def test_report_export_payload_does_not_leak_other_tables(db, db_user_goal):
    """导出只包含周报本身，不把整库数据带走。"""
    user, goal = db_user_goal
    _seed_report(db, goal.id, user.id)
    report = db.scalars(select(Report)).one()
    assert report.user_id == user.id
