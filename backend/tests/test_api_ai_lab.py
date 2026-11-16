"""AI 探针、思维回放、评审团、时效雷达、证据链与认知负荷接口测试。

覆盖鉴权、参数校验、资源归属、生成/作答/回读闭环，并显式验证
未配置 LLM 时不会发起任何真实 DeepSeek 请求。
"""

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import (
    Evidence,
    FreshnessReport,
    Material,
    Mistake,
    PanelReview,
    ProbeItem,
    ThoughtTrace,
    User,
)


def _tester(db):
    return db.scalars(select(User).where(User.username == "tester")).one()


def _register(api, username):
    response = api(
        "POST",
        "/api/auth/register",
        json={"username": username, "password": "secret123", "nickname": username},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mistake(db, auth, goal_id, category="concept", label="概念不清"):
    item = Mistake(
        user_id=auth["user"]["id"],
        goal_id=goal_id,
        question="请选出正确的时态",
        user_answer="A",
        correct_answer="B",
        category=category,
        category_label=label,
    )
    db.add(item)
    db.commit()
    return item


def _generate(api, token, goal_id, kind="probe", count=1, kp_id=None):
    payload = {"kind": kind, "count": count}
    if kp_id is not None:
        payload["kp_id"] = kp_id
    return api("POST", "/api/goals/%d/probes/generate" % goal_id, token=token, json=payload)


# --------------------------------------------------------------------------
# 鉴权与目标校验
# --------------------------------------------------------------------------


def test_ai_lab_endpoints_require_authentication(api, goal):
    goal_id = goal["id"]
    assert api("GET", "/api/goals/%d/probes" % goal_id).status_code == 401
    assert api("POST", "/api/goals/%d/probes/generate" % goal_id, json={"kind": "probe"}).status_code == 401
    assert api("POST", "/api/probes/1/submit", json={"chosen": 0}).status_code == 401
    assert api("GET", "/api/mistakes/1/trace").status_code == 401
    assert api("POST", "/api/goals/%d/panel/review" % goal_id, json={}).status_code == 401
    assert api("GET", "/api/goals/%d/freshness" % goal_id).status_code == 401
    assert api("POST", "/api/goals/%d/freshness/scan" % goal_id).status_code == 401
    assert api("GET", "/api/goals/%d/evidence" % goal_id).status_code == 401
    assert api("GET", "/api/goals/%d/cognitive-load" % goal_id).status_code == 401
    assert api("POST", "/api/goals/%d/cognitive-load/apply" % goal_id, json={}).status_code == 401


def test_ai_lab_rejects_unknown_goal(api, auth):
    token = auth["token"]
    missing = api("GET", "/api/goals/99999/probes", token=token)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "目标不存在"

    assert api("POST", "/api/goals/99999/panel/review", token=token, json={}).status_code == 404
    assert api("POST", "/api/goals/99999/freshness/scan", token=token).status_code == 404
    assert api("GET", "/api/goals/99999/freshness", token=token).status_code == 404
    assert api("GET", "/api/goals/99999/cognitive-load", token=token).status_code == 404
    assert api("GET", "/api/goals/99999/evidence", token=token).status_code == 404


def test_rule_paths_never_invoke_llm(api, auth, goal, imported_points, db, monkeypatch):
    """未配置 LLM 时，各 AI 入口都走规则分支，不得发生任何模型调用。"""
    from app import llm as llm_module

    calls = []

    async def spy_chat_json(system, user):
        calls.append((system, user))
        return None

    monkeypatch.setattr(llm_module.llm, "chat_json", spy_chat_json)
    assert llm_module.llm.available is False

    token = auth["token"]
    goal_id = goal["id"]
    assert _generate(api, token, goal_id).status_code == 200
    assert api("POST", "/api/goals/%d/freshness/scan" % goal_id, token=token).status_code == 200
    assert api(
        "POST", "/api/goals/%d/panel/review" % goal_id, token=token, json={"topic": "今天学什么"}
    ).status_code == 200
    mistake = _mistake(db, auth, goal_id)
    assert api("POST", "/api/mistakes/%d/trace" % mistake.id, token=token).status_code == 200

    assert calls == []


# --------------------------------------------------------------------------
# 探针
# --------------------------------------------------------------------------


def test_generate_probes_without_points_returns_400(api, auth, goal):
    response = _generate(api, auth["token"], goal["id"])

    assert response.status_code == 400
    assert response.json()["detail"] == "还没有知识点，请先导入资料"


def test_generate_probes_rejects_unknown_kind(api, auth, goal, imported_points):
    response = _generate(api, auth["token"], goal["id"], kind="invalid")

    assert response.status_code == 400
    assert response.json()["detail"] == "探针类型必须是 probe / transfer / challenge"


def test_generated_probes_are_listed_and_filterable(api, auth, goal, imported_points):
    token = auth["token"]
    goal_id = goal["id"]

    created = _generate(api, token, goal_id, kind="probe", count=2)
    assert created.status_code == 200, created.text
    body = created.json()
    assert len(body) == 2
    assert all(item["kind"] == "probe" for item in body)
    assert all(item["status"] == "pending" for item in body)
    assert all(len(item["options"]) == 4 for item in body)
    assert all(item["kp_name"] for item in body)
    assert all(item["explanation"] for item in body)

    probes = api("GET", "/api/goals/%d/probes?kind=probe" % goal_id, token=token)
    assert probes.status_code == 200
    assert len(probes.json()) == 2
    assert api("GET", "/api/goals/%d/probes?kind=transfer" % goal_id, token=token).json() == []
    assert api("GET", "/api/goals/%d/probes?status=answered" % goal_id, token=token).json() == []

    limited = api("GET", "/api/goals/%d/probes?limit=1" % goal_id, token=token)
    assert len(limited.json()) == 1

    transfer = _generate(api, token, goal_id, kind="transfer", count=1)
    assert transfer.status_code == 200
    assert transfer.json()[0]["kind"] == "transfer"


def test_generate_probes_targets_specific_point(api, auth, goal, imported_points):
    # 只对叶子知识点出题，避免命中父节点后被回退到第一个叶子
    target = next(item["id"] for item in imported_points if item["name"] == "短对话")

    response = _generate(api, auth["token"], goal["id"], count=3, kp_id=target)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["kp_id"] == target


def test_probe_generate_count_out_of_range(api, auth, goal, imported_points):
    response = _generate(api, auth["token"], goal["id"], count=4)

    assert response.status_code == 422


def test_submit_probe_correct_answer_flow(api, auth, goal, imported_points, db):
    token = auth["token"]
    goal_id = goal["id"]
    probe_id = _generate(api, token, goal_id).json()[0]["id"]
    stored = db.get(ProbeItem, probe_id)
    chosen = stored.answer_index


    response = api("POST", "/api/probes/%d/submit" % probe_id, token=token, json={"chosen": chosen})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["correct"] is True
    assert body["mastery"] == 0.08
    assert body["resilience"] == 2
    assert body["evidence"] == "已写入学习证据链"

    db.expire_all()
    answered = db.get(ProbeItem, probe_id)
    assert answered.status == "answered"
    assert answered.chosen_index == chosen
    assert answered.correct is True
    assert answered.answered_at is not None

    again = api("POST", "/api/probes/%d/submit" % probe_id, token=token, json={"chosen": chosen})
    assert again.status_code == 400
    assert again.json()["detail"] == "这道题已经作答"


def test_submit_probe_rejects_unknown_and_foreign_item(api, auth, goal, imported_points, db):
    token = auth["token"]
    probe_id = _generate(api, token, goal["id"]).json()[0]["id"]

    missing = api("POST", "/api/probes/99999/submit", token=token, json={"chosen": 0})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "探针题不存在"

    other = _register(api, "other-user")
    stored = db.get(ProbeItem, probe_id)
    stored.user_id = other["user"]["id"]
    db.commit()

    foreign = api("POST", "/api/probes/%d/submit" % probe_id, token=token, json={"chosen": 0})
    assert foreign.status_code == 404
    assert foreign.json()["detail"] == "探针题不存在"


def test_submit_probe_validates_chosen_index(api, auth, goal, imported_points):
    token = auth["token"]
    probe_id = _generate(api, token, goal["id"]).json()[0]["id"]

    assert api("POST", "/api/probes/%d/submit" % probe_id, token=token, json={"chosen": 4}).status_code == 422
    assert api("POST", "/api/probes/%d/submit" % probe_id, token=token, json={"chosen": -1}).status_code == 422


# --------------------------------------------------------------------------
# 思维路径回放
# --------------------------------------------------------------------------


def test_trace_create_and_read_are_idempotent(api, auth, goal, db):
    token = auth["token"]
    mistake = _mistake(db, auth, goal["id"], "method", "方法不会")

    created = api("POST", "/api/mistakes/%d/trace" % mistake.id, token=token)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["mistake_id"] == mistake.id
    assert body["engine"] == "rule"
    assert body["error_step"] == 1
    assert len(body["steps"]) == 4
    assert body["steps"][1]["verdict"] == "偏离"
    assert body["summary"].startswith("错误发生在第 2 步")

    again = api("POST", "/api/mistakes/%d/trace" % mistake.id, token=token)
    assert again.status_code == 200
    assert again.json()["steps"] == body["steps"]
    assert len(db.scalars(select(ThoughtTrace)).all()) == 1

    read = api("GET", "/api/mistakes/%d/trace" % mistake.id, token=token)
    assert read.status_code == 200
    assert read.json() == body


def test_trace_rejects_unknown_and_foreign_mistake(api, auth, goal, db):
    token = auth["token"]
    missing = api("GET", "/api/mistakes/99999/trace", token=token)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "错题不存在"

    other = _register(api, "trace-owner")
    mistake = _mistake(db, auth, goal["id"])
    mistake.user_id = other["user"]["id"]
    db.commit()

    foreign = api("POST", "/api/mistakes/%d/trace" % mistake.id, token=token)
    assert foreign.status_code == 404
    assert foreign.json()["detail"] == "错题不存在"


def test_trace_read_before_creation_returns_404(api, auth, goal, db):
    token = auth["token"]
    mistake = _mistake(db, auth, goal["id"])

    response = api("GET", "/api/mistakes/%d/trace" % mistake.id, token=token)

    assert response.status_code == 404
    assert response.json()["detail"] == "尚未生成思维路径回放"


# --------------------------------------------------------------------------
# 多智能体评审团
# --------------------------------------------------------------------------


def test_panel_review_creates_record_and_history(api, auth, goal, imported_points, db):
    token = auth["token"]
    goal_id = goal["id"]

    created = api(
        "POST", "/api/goals/%d/panel/review" % goal_id, token=token, json={"topic": "今天要不要加题"}
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["topic"] == "今天要不要加题"
    assert [item["role"] for item in body["opinions"]] == ["计划官", "诊断官", "风险官", "教练"]
    assert len(body["votes"]) == 4
    assert body["engine"] == "rule"
    assert body["verdict"].startswith("评审团建议：")
    assert db.get(PanelReview, body["id"]) is not None

    history = api("GET", "/api/goals/%d/panel/reviews" % goal_id, token=token)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["topic"] == "今天要不要加题"

    limited = api("GET", "/api/goals/%d/panel/reviews?limit=1" % goal_id, token=token)
    assert len(limited.json()) == 1
    assert api("GET", "/api/goals/%d/panel/reviews?limit=0" % goal_id, token=token).status_code == 422


def test_panel_review_uses_default_topic(api, auth, goal):
    response = api("POST", "/api/goals/%d/panel/review" % goal["id"], token=auth["token"], json={})

    assert response.status_code == 200
    assert response.json()["topic"] == "今日学习计划"


def test_panel_review_rejects_too_long_topic(api, auth, goal):
    response = api(
        "POST",
        "/api/goals/%d/panel/review" % goal["id"],
        token=auth["token"],
        json={"topic": "长" * 121},
    )

    assert response.status_code == 422


def test_panel_history_tolerates_broken_json(api, auth, goal, db):
    db.add(
        PanelReview(
            user_id=auth["user"]["id"],
            goal_id=goal["id"],
            topic="坏数据",
            opinions="{bad",
            verdict="",
            votes="{bad",
        )
    )
    db.commit()

    response = api("GET", "/api/goals/%d/panel/reviews" % goal["id"], token=auth["token"])

    assert response.status_code == 200
    body = response.json()
    assert body[0]["opinions"] == []
    assert body[0]["votes"] == []
    assert body[0]["topic"] == "坏数据"


# --------------------------------------------------------------------------
# 内容时效雷达
# --------------------------------------------------------------------------


def test_freshness_scan_without_materials(api, auth, goal):
    token = auth["token"]
    goal_id = goal["id"]

    scanned = api("POST", "/api/goals/%d/freshness/scan" % goal_id, token=token)
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["items"] == []
    assert scanned.json()["overall"] == 0

    stored = api("GET", "/api/goals/%d/freshness" % goal_id, token=token)
    assert stored.status_code == 200
    assert stored.json()["items"] == []
    assert stored.json()["overall"] == 0
    assert stored.json()["scanned_at"] is None


def test_freshness_read_tolerates_broken_issues(api, auth, goal, db):
    material = Material(
        user_id=auth["user"]["id"], goal_id=goal["id"], filename="资料.txt", content="x"
    )
    db.add(material)
    db.flush()
    db.add(
        FreshnessReport(
            user_id=auth["user"]["id"],
            goal_id=goal["id"],
            material_id=material.id,
            score=90,
            issues="{bad",
            suggestion="补充真题",
            engine="rule",
        )
    )
    db.commit()

    response = api("GET", "/api/goals/%d/freshness" % goal["id"], token=auth["token"])

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["issues"] == []
    assert body["items"][0]["filename"] == "资料.txt"
    assert body["items"][0]["level"] == "fresh"
    assert body["overall"] == 90
    assert body["scanned_at"] is not None


def test_freshness_scan_and_read(api, auth, goal, imported_points):
    token = auth["token"]
    goal_id = goal["id"]

    scanned = api("POST", "/api/goals/%d/freshness/scan" % goal_id, token=token)
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["filename"] == "四级大纲"
    assert item["score"] == 55
    assert item["level"] == "stale"
    assert item["engine"] == "rule"
    assert "未发现考纲对照" in item["issues"][1]
    assert body["overall"] == 55
    assert body["scanned_at"] is not None

    stored = api("GET", "/api/goals/%d/freshness" % goal_id, token=token)
    assert stored.status_code == 200
    assert stored.json()["items"][0]["score"] == item["score"]
    assert stored.json()["overall"] == 55


def test_freshness_read_uses_placeholder_for_removed_material(
    api, auth, goal, imported_points, db
):
    token = auth["token"]
    goal_id = goal["id"]
    assert api("POST", "/api/goals/%d/freshness/scan" % goal_id, token=token).status_code == 200
    report = db.scalars(select(FreshnessReport)).one()
    material_id = report.material_id

    db.query(Material).delete()
    db.commit()

    response = api("GET", "/api/goals/%d/freshness" % goal_id, token=token)

    assert response.status_code == 200
    assert response.json()["items"][0]["filename"] == "资料 %d" % material_id


# --------------------------------------------------------------------------
# 学习证据链
# --------------------------------------------------------------------------


def test_evidence_chain_records_probe_generation(api, auth, goal, imported_points):
    token = auth["token"]
    goal_id = goal["id"]

    empty = api("GET", "/api/goals/%d/evidence" % goal_id, token=token)
    assert empty.status_code == 200
    assert empty.json() == []

    assert _generate(api, token, goal_id, count=2).status_code == 200

    listed = api("GET", "/api/goals/%d/evidence" % goal_id, token=token)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["kind"] == "probe_generate"
    assert rows[0]["engine"] == "rule"
    assert rows[0]["payload"]["count"] == 2
    assert rows[0]["output"].startswith("生成 2 道")
    assert rows[0]["created_at"]

    assert len(api("GET", "/api/goals/%d/evidence?kind=probe_generate" % goal_id, token=token).json()) == 1
    assert api("GET", "/api/goals/%d/evidence?kind=panel_review" % goal_id, token=token).json() == []


def test_evidence_chain_limit_validation(api, auth, goal, imported_points):
    token = auth["token"]
    goal_id = goal["id"]
    assert _generate(api, token, goal_id).status_code == 200

    assert api("GET", "/api/goals/%d/evidence?limit=0" % goal_id, token=token).status_code == 422
    assert api("GET", "/api/goals/%d/evidence?limit=101" % goal_id, token=token).status_code == 422
    assert len(api("GET", "/api/goals/%d/evidence?limit=1" % goal_id, token=token).json()) == 1


def test_evidence_chain_isolated_between_users(api, auth, goal, imported_points, db):
    token = auth["token"]
    assert _generate(api, token, goal["id"]).status_code == 200

    other = _register(api, "evidence-owner")
    other_goal = api(
        "POST",
        "/api/goals",
        token=other["access_token"],
        json={
            "exam_name": "考研数学",
            "exam_date": (date.today() + timedelta(days=60)).isoformat(),
            "daily_minutes": 60,
        },
    )
    assert other_goal.status_code == 201, other_goal.text

    rows = api(
        "GET", "/api/goals/%d/evidence" % other_goal.json()["id"], token=other["access_token"]
    )
    assert rows.status_code == 200
    assert rows.json() == []


# --------------------------------------------------------------------------
# 认知负荷调节
# --------------------------------------------------------------------------


def test_cognitive_load_read_and_auto_apply(api, auth, goal, db):
    token = auth["token"]
    goal_id = goal["id"]

    current = api("GET", "/api/goals/%d/cognitive-load" % goal_id, token=token)
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["score"] == 0
    assert body["level"] == "low"
    assert len(body["factors"]) == 4
    assert body["recommended_tasks"] == 3
    assert body["recommended_minutes"] == 110

    applied = api(
        "POST", "/api/goals/%d/cognitive-load/apply" % goal_id, token=token, json={"action": "auto"}
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["action"] == "increase"
    assert result["before"]["level"] == "low"
    assert result["message"] == "已加入 1 个 20 分钟迁移挑战任务。"
    assert result["changes"][0]["kind"] == "increase"
    assert result["after"]["factors"][1] == "今日任务 1 个 / 20 分钟"

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "cognitive_load")).one()
    assert json.loads(evidence.payload)["action"] == "increase"


def test_cognitive_load_explicit_keep(api, auth, goal):
    token = auth["token"]
    goal_id = goal["id"]

    response = api(
        "POST", "/api/goals/%d/cognitive-load/apply" % goal_id, token=token, json={"action": "keep"}
    )

    assert response.status_code == 200
    assert response.json()["action"] == "keep"
    assert response.json()["changes"] == []


def test_cognitive_load_rejects_invalid_action(api, auth, goal):
    response = api(
        "POST",
        "/api/goals/%d/cognitive-load/apply" % goal["id"],
        token=auth["token"],
        json={"action": "x" * 17},
    )

    assert response.status_code == 422