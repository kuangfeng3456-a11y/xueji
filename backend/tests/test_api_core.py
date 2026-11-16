from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Mistake, User
from app.security import create_access_token


def test_health_meta_and_skills(api):
    health = api("GET", "/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    meta = api("GET", "/api/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["cache_backend"] == "memory"
    assert body["llm_enabled"] is False
    assert body["llm_model"] is None
    assert len(body["skills"]) == 8
    assert "skill-package-builder" in body["skills"]

    skills = api("GET", "/api/skills")
    assert skills.status_code == 200
    assert skills.json()["count"] == 8


def test_register_login_and_profile(api):
    response = api(
        "POST",
        "/api/auth/register",
        json={"username": "alice", "password": "secret123", "nickname": "小林", "school": "计算机学院"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["nickname"] == "小林"
    assert payload["user"]["school"] == "计算机学院"
    token = payload["access_token"]

    profile = api("GET", "/api/auth/me", token=token)
    assert profile.status_code == 200
    assert profile.json()["username"] == "alice"

    login = api("POST", "/api/auth/login", json={"username": "alice", "password": "secret123"})
    assert login.status_code == 200
    assert login.json()["user"]["id"] == payload["user"]["id"]

    wrong = api("POST", "/api/auth/login", json={"username": "alice", "password": "bad-password"})
    assert wrong.status_code == 400
    assert "用户名或密码错误" in wrong.json()["detail"]

    unknown = api("POST", "/api/auth/login", json={"username": "nobody", "password": "secret123"})
    assert unknown.status_code == 400


def test_register_rejects_duplicate_and_invalid_input(api):
    payload = {"username": "bob", "password": "secret123"}
    assert api("POST", "/api/auth/register", json=payload).status_code == 201

    duplicate = api("POST", "/api/auth/register", json=payload)
    assert duplicate.status_code == 400
    assert "已被注册" in duplicate.json()["detail"]

    bad_name = api("POST", "/api/auth/register", json={"username": "bad name", "password": "secret123"})
    assert bad_name.status_code == 422

    short_password = api("POST", "/api/auth/register", json={"username": "carol", "password": "123"})
    assert short_password.status_code == 422


def test_auth_guards(api):
    assert api("GET", "/api/auth/me").status_code == 401
    assert api("GET", "/api/auth/me", token="not-a-jwt").status_code == 401

    ghost_token = create_access_token(99999, "ghost")
    assert api("GET", "/api/auth/me", token=ghost_token).status_code == 401


def test_goal_crud(api, auth, db):
    token = auth["token"]
    exam_date = (date.today() + timedelta(days=12)).isoformat()
    created = api(
        "POST",
        "/api/goals",
        token=token,
        json={"exam_name": "大学英语四级", "exam_date": exam_date, "daily_minutes": 60},
    )
    assert created.status_code == 201
    goal = created.json()
    assert goal["days_left"] == 12
    assert goal["knowledge_count"] == 0
    assert goal["avg_mastery"] == 0.0
    assert goal["completed_rate"] == 0.0

    listed = api("GET", "/api/goals", token=token)
    assert [item["id"] for item in listed.json()] == [goal["id"]]

    # 单个目标详情：days_left 随当天日期动态计算，不是建库时写死的快照
    detail = api("GET", f"/api/goals/{goal['id']}", token=token)
    assert detail.status_code == 200
    assert detail.json()["exam_name"] == "大学英语四级"
    assert detail.json()["days_left"] == 12

    updated = api(
        "PUT",
        f"/api/goals/{goal['id']}",
        token=token,
        json={"exam_name": "大学英语六级", "exam_date": exam_date, "daily_minutes": 120},
    )
    assert updated.status_code == 200
    assert updated.json()["exam_name"] == "大学英语六级"
    assert updated.json()["daily_minutes"] == 120

    assert api("DELETE", f"/api/goals/{goal['id']}", token=token).status_code == 204
    assert api("DELETE", f"/api/goals/{goal['id']}", token=token).status_code == 404
    assert db.query(User).count() == 1


def test_goal_rejects_past_date(api, auth):
    response = api(
        "POST",
        "/api/goals",
        token=auth["token"],
        json={
            "exam_name": "无效目标",
            "exam_date": (date.today() - timedelta(days=1)).isoformat(),
            "daily_minutes": 60,
        },
    )
    assert response.status_code == 422


def test_goal_isolation_between_users(api, auth, goal):
    other = api("POST", "/api/auth/register", json={"username": "other", "password": "secret123"})
    other_token = other.json()["access_token"]

    assert api("GET", "/api/goals", token=other_token).json() == []
    assert api("GET", f"/api/goals/{goal['id']}/knowledge-points", token=other_token).status_code == 404
    assert api("GET", "/api/goals/{}/rhythm".format(goal["id"]), token=other_token).status_code == 404


def test_import_text_builds_knowledge_tree(api, auth, goal, imported_points):
    token = auth["token"]
    assert len(imported_points) == 10
    parents = [item for item in imported_points if item["parent_id"] is None]
    children = [item for item in imported_points if item["parent_id"] is not None]
    assert len(parents) == 3
    assert len(children) == 7
    assert all(item["mastery"] == 0.0 for item in imported_points)

    listed = api("GET", f"/api/goals/{goal['id']}/knowledge-points", token=token)
    assert listed.status_code == 200
    assert len(listed.json()) == 10
    weights = [item["weight"] for item in listed.json()]
    assert weights == sorted(weights, reverse=True)

    materials = api("GET", f"/api/goals/{goal['id']}/materials", token=token)
    assert materials.status_code == 200
    assert materials.json()[0]["filename"] == "四级大纲"


def test_import_text_rejects_empty_content(api, auth, goal):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/materials/text",
        token=auth["token"],
        json={"filename": "空资料", "content": "   "},
    )
    assert response.status_code == 400
    assert "知识点" in response.json()["detail"]


def test_knowledge_point_manual_crud(api, auth, goal, imported_points):
    token = auth["token"]
    duplicate = api(
        "POST",
        f"/api/goals/{goal['id']}/knowledge-points",
        token=token,
        json={"name": "听力", "weight": 1.2},
    )
    assert duplicate.status_code == 400
    assert "已存在" in duplicate.json()["detail"]

    bad_parent = api(
        "POST",
        f"/api/goals/{goal['id']}/knowledge-points",
        token=token,
        json={"name": "口语", "parent_id": 99999},
    )
    assert bad_parent.status_code == 400

    parent_id = imported_points[0]["id"]
    created = api(
        "POST",
        f"/api/goals/{goal['id']}/knowledge-points",
        token=token,
        json={"name": "口语表达", "parent_id": parent_id, "weight": 1.1},
    )
    assert created.status_code == 201
    assert created.json()["parent_id"] == parent_id
    assert created.json()["mastery"] == 0.0

    assert api(
        "DELETE", f"/api/goals/{goal['id']}/knowledge-points/{created.json()['id']}", token=token
    ).status_code == 204
    assert api(
        "DELETE", f"/api/goals/{goal['id']}/knowledge-points/99999", token=token
    ).status_code == 404


def test_import_file_upload(api, auth, goal):
    token = auth["token"]
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/materials/upload",
        token=token,
        files={"file": ("outline.txt", "# 听力\n- 短对话\n- 长对话\n".encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    names = [item["name"] for item in response.json()]
    assert names == ["听力", "短对话", "长对话"]


def test_import_file_rejects_bad_format_and_oversize(api, auth, goal, monkeypatch):
    token = auth["token"]
    unsupported = api(
        "POST",
        f"/api/goals/{goal['id']}/materials/upload",
        token=token,
        files={"file": ("notes.xlsx", b"binary", "application/vnd.ms-excel")},
    )
    assert unsupported.status_code == 400
    assert "仅支持" in unsupported.json()["detail"]

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 8)
    oversize = api(
        "POST",
        f"/api/goals/{goal['id']}/materials/upload",
        token=token,
        files={"file": ("big.txt", b"1234567890", "text/plain")},
    )
    assert oversize.status_code == 400
    assert "5MB" in oversize.json()["detail"]

    empty = api(
        "POST",
        f"/api/goals/{goal['id']}/materials/upload",
        token=token,
        files={"file": ("empty.txt", b"   ", "text/plain")},
    )
    assert empty.status_code == 400


def test_export_and_delete_account(api, auth, goal, imported_points):
    token = auth["token"]
    assert api("GET", "/api/auth/me/export").status_code == 401

    kp_id = imported_points[0]["id"]
    assert api("POST", f"/api/goals/{goal['id']}/plan", token=token, json={"days": 1}).status_code == 200
    assert api(
        "POST", f"/api/goals/{goal['id']}/mastery/{kp_id}/answer", token=token, json={"correct": True}
    ).status_code == 200
    assert api(
        "POST",
        f"/api/goals/{goal['id']}/mistakes",
        token=token,
        json={"question": "请计算", "user_answer": "不会", "correct_answer": "0", "kp_id": kp_id},
    ).status_code == 201
    assert api("POST", f"/api/goals/{goal['id']}/reports", token=token).status_code == 200

    exported = api("GET", "/api/auth/me/export", token=token)
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["user"]["username"] == "tester"
    assert len(body["goals"]) == 1
    assert len(body["knowledge_points"]) == 10
    assert body["knowledge_points"][0]["goal_id"] == goal["id"]
    assert body["mastery"] and body["mastery"][0]["value"] == 0.0957
    assert body["mastery_history"]
    assert body["tasks"] and body["tasks"][0]["title"]
    assert body["mistakes"] and body["mistakes"][0]["category"] == "method"
    assert body["materials"]
    assert body["reports"] and body["reports"][0]["content"]
    assert body["replan_logs"] and body["replan_logs"][0]["trigger"]
    assert body["exported_at"].endswith("Z")

    deleted = api("DELETE", "/api/auth/me", token=token)
    assert deleted.status_code == 204
    assert api("GET", "/api/auth/me", token=token).status_code == 401
    assert api("POST", "/api/auth/login", json={"username": "tester", "password": "secret123"}).status_code == 400


def test_delete_account_removes_related_rows(api, auth, goal, imported_points, db):
    from app.models import Goal, KnowledgePoint, Task

    token = auth["token"]
    plan = api("POST", f"/api/goals/{goal['id']}/plan", token=token, json={"days": 2})
    assert plan.status_code == 200
    assert db.query(Task).count() > 0

    assert api("DELETE", "/api/auth/me", token=token).status_code == 204
    assert db.query(User).count() == 0
    assert db.query(Goal).count() == 0
    assert db.query(KnowledgePoint).count() == 0
    assert db.query(Task).count() == 0

def test_mistake_summary_uses_full_dataset_not_page(api, auth, goal, db):
    """把库填到超过列表默认 20 条，summary 必须返回全量总数与四类分布。"""
    token = auth["token"]
    goal_id = goal["id"]
    for index in range(25):
        created = api(
            "POST",
            "/api/goals/%d/mistakes" % goal_id,
            token=token,
            json={"question": "题目 %d" % index, "user_answer": "A", "correct_answer": "B"},
        )
        assert created.status_code == 201, created.text

    # 接口不接受 category（由诊断决定），这里直接落库固定分布，验证聚合口径
    rows = db.execute(select(Mistake).where(Mistake.goal_id == goal_id).order_by(Mistake.id)).scalars().all()
    plan = ["concept"] * 7 + ["method"] * 6 + ["careless"] * 6 + ["time"] * 6
    for row, category in zip(rows, plan):
        row.category = category
    db.commit()

    listing = api("GET", "/api/goals/%d/mistakes" % goal_id, token=token).json()
    assert len(listing) == 20, "列表默认只返回最近 20 条"

    summary = api("GET", "/api/goals/%d/mistakes/summary" % goal_id, token=token).json()
    assert summary["total"] == 25
    assert summary["by_category"] == {"concept": 7, "method": 6, "careless": 6, "time": 6}
    assert summary["last_7_days"] == 25
    assert summary["point_total"] >= 0
