"""学习证据链服务单元测试。

覆盖写入语义（flush / commit）、字段与载荷截断、非 JSON 值的序列化、
按类型与数量过滤、跨用户隔离以及坏数据容错。
"""

import json
from datetime import date, datetime
from datetime import timedelta

from sqlalchemy import select

from app.models import Evidence, Goal, User
from app.security import hash_password
from app.services.evidence import list_evidence, record_evidence


def test_record_evidence_flushes_without_commit(db, db_user_goal):
    user, goal = db_user_goal

    evidence = record_evidence(
        db,
        user.id,
        goal.id,
        "probe_answer",
        "第 1 题",
        {"chosen": 2},
        "答对了",
        engine="llm",
    )

    assert evidence.id is not None
    assert evidence.kind == "probe_answer"
    assert evidence.subject == "第 1 题"
    assert evidence.engine == "llm"
    assert evidence.output == "答对了"
    payload = json.loads(evidence.payload)
    assert payload["chosen"] == 2
    assert payload["validation"] == "passed"
    assert payload["fallback"] is False
    assert "snapshot_id" in payload

    db.rollback()
    assert db.scalars(select(Evidence)).all() == []


def test_record_evidence_commit_refreshes_record(db, db_user_goal):
    user, goal = db_user_goal

    evidence = record_evidence(
        db, user.id, goal.id, "panel_review", "议题", {}, "结论", commit=True
    )

    assert evidence.id is not None
    assert evidence.created_at is not None
    assert db.scalars(select(Evidence)).all() == [evidence]


def test_record_evidence_truncates_subject_and_output(db, db_user_goal):
    user, goal = db_user_goal

    evidence = record_evidence(
        db, user.id, goal.id, "trace", "主" * 300, {}, "输" * 3000
    )

    assert len(evidence.subject) == 120
    assert len(evidence.output) == 2000


def test_record_evidence_normalizes_empty_output(db, db_user_goal):
    user, goal = db_user_goal

    evidence = record_evidence(db, user.id, goal.id, "trace", "题目", {}, None)

    assert evidence.output == ""


def test_record_evidence_serializes_dates_with_default_str(db, db_user_goal):
    user, goal = db_user_goal

    evidence = record_evidence(
        db,
        user.id,
        goal.id,
        "scan",
        "资料",
        {"when": datetime(2026, 1, 2, 8, 30), "day": date(2026, 1, 2)},
        "完成",
    )

    payload = json.loads(evidence.payload)
    assert payload["when"] == "2026-01-02 08:30:00"
    assert payload["day"] == "2026-01-02"


def test_record_evidence_truncates_large_payload(db, db_user_goal):
    user, goal = db_user_goal

    evidence = record_evidence(
        db, user.id, goal.id, "scan", "资料", {"big": "x" * 7000}, "完成"
    )

    assert len(evidence.payload) == 6000
    # 截断后的载荷不再合法，读取侧应容错为空字典
    listed = list_evidence(db, user, goal.id)
    assert listed[0]["payload"] == {}


def test_list_evidence_sorts_by_created_at_desc(db, db_user_goal):
    user, goal = db_user_goal
    base = datetime(2026, 3, 1, 9, 0, 0)
    for index, kind in enumerate(["first", "second", "third"]):
        row = Evidence(
            user_id=user.id,
            goal_id=goal.id,
            kind=kind,
            subject=kind,
            payload="{}",
            output=kind,
            created_at=base + timedelta(minutes=index),
        )
        db.add(row)
    db.commit()

    listed = list_evidence(db, user, goal.id)

    assert [item["kind"] for item in listed] == ["third", "second", "first"]
    assert listed[0]["created_at"] == base + timedelta(minutes=2)
    assert listed[0]["output"] == "third"


def test_list_evidence_filters_by_kind_and_limit(db, db_user_goal):
    user, goal = db_user_goal
    for index in range(3):
        record_evidence(db, user.id, goal.id, "probe_answer", "题%s" % index, {}, "o")
    record_evidence(db, user.id, goal.id, "panel_review", "议题", {}, "o")
    db.commit()

    filtered = list_evidence(db, user, goal.id, kind="probe_answer")
    limited = list_evidence(db, user, goal.id, limit=2)
    missing = list_evidence(db, user, goal.id, kind="not-exist")

    assert len(filtered) == 3
    assert {item["kind"] for item in filtered} == {"probe_answer"}
    assert len(limited) == 2
    assert missing == []


def test_list_evidence_isolates_users(db, db_user_goal):
    user, goal = db_user_goal
    other = User(username="other", password_hash=hash_password("secret123"), nickname="别人")
    db.add(other)
    db.flush()
    other_goal = Goal(
        user_id=other.id,
        exam_name="考研",
        exam_date=date.today() + timedelta(days=50),
        daily_minutes=120,
    )
    db.add(other_goal)
    db.flush()

    record_evidence(db, user.id, goal.id, "probe_answer", "我的证据", {}, "ok")
    record_evidence(db, other.id, other_goal.id, "probe_answer", "别人的证据", {}, "ok")
    record_evidence(db, other.id, other_goal.id, "panel_review", "别人的议题", {}, "ok")
    db.commit()

    mine = list_evidence(db, user, goal.id)
    other_goal_rows = list_evidence(db, other, other_goal.id)

    assert [item["subject"] for item in mine] == ["我的证据"]
    assert len(other_goal_rows) == 2


def test_list_evidence_tolerates_broken_payload(db, db_user_goal):
    user, goal = db_user_goal
    db.add(
        Evidence(
            user_id=user.id,
            goal_id=goal.id,
            kind="broken",
            subject="坏数据",
            payload="{not-json",
            output="",
        )
    )
    db.commit()

    listed = list_evidence(db, user, goal.id)

    assert listed[0]["payload"] == {}
    assert listed[0]["subject"] == "坏数据"