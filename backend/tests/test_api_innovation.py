"""11.docx 创新功能 API 单元测试。

覆盖 cockpit / knowledge / risks / experiments / twin 五组接口，
并显式验证测试期间不会触发真实 DeepSeek 调用。
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.cache import cache
from app.models import (
    Goal,
    KnowledgeGap,
    KnowledgePoint,
    LearningExperiment,
    Mastery,
    Mistake,
    ReplanLog,
    Task,
    User,
)

GOAL_PAYLOAD = {
    "exam_name": "HCIA 认证",
    "exam_date": (date.today() + timedelta(days=40)).isoformat(),
    "daily_minutes": 90,
}


# --------------------------------------------------------------------------
# 测试数据辅助
# --------------------------------------------------------------------------


def _tester(db):
    return db.scalars(select(User).where(User.username == "tester")).one()


def _point_id(imported_points, name):
    return next(item["id"] for item in imported_points if item["name"] == name)


def _task(db, user, goal_id, day=None, status="pending", minutes=30, priority=1.0):
    task = Task(
        user_id=user.id,
        goal_id=goal_id,
        day=day or date.today(),
        title="关键任务",
        type="study",
        duration_min=minutes,
        status=status,
        reason="测试",
        priority=priority,
        source="plan",
    )
    db.add(task)
    db.flush()
    return task


def _mistake(db, user, goal_id, kp_id):
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal_id,
            kp_id=kp_id,
            question="子网划分题目",
            user_answer="错误答案",
            correct_answer="正确答案",
            category="concept",
            category_label="概念不清",
        )
    )


def _healthy_mastery(db, user, imported_points, low_name=None):
    # 导入知识点时会初始化 0.0 的掌握度记录，这里需要复用而不是重复插入
    rows = {
        row.kp_id: row
        for row in db.scalars(select(Mastery).where(Mastery.user_id == user.id)).all()
    }
    for item in imported_points:
        value = 0.2 if item["name"] == low_name else 0.9
        row = rows.get(item["id"])
        if row is None:
            db.add(Mastery(user_id=user.id, kp_id=item["id"], value=value))
        else:
            row.value = value
    db.flush()


def _seed_candidate(db, user, goal_id, imported_points, leaf_name):
    """让指定叶子节点命中“错题反复 + 掌握度低”的候选漏洞规则。"""
    _healthy_mastery(db, user, imported_points, low_name=leaf_name)
    leaf_id = _point_id(imported_points, leaf_name)
    _mistake(db, user, goal_id, leaf_id)
    _mistake(db, user, goal_id, leaf_id)
    db.commit()
    return leaf_id


def _candidate_gap_id(api, token, goal_id):
    response = api("GET", "/api/goals/%d/knowledge-graph" % goal_id, token=token)
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]
    assert len(candidates) == 1
    return candidates[0]["id"]


# --------------------------------------------------------------------------
# 学习驾驶舱
# --------------------------------------------------------------------------


def test_cockpit_endpoint_aggregates_readiness_risks_and_counts(
    api, auth, goal, imported_points, db
):
    user = _tester(db)
    goal_id = goal["id"]
    _healthy_mastery(db, user, imported_points)
    candidate = _point_id(imported_points, "短对话")
    verified_one = _point_id(imported_points, "长对话")
    verified_two = _point_id(imported_points, "听力篇章")
    db.add(
        KnowledgeGap(
            user_id=user.id, goal_id=goal_id, kp_id=candidate, status="candidate", evidence="候选"
        )
    )
    db.add_all(
        [
            KnowledgeGap(
                user_id=user.id, goal_id=goal_id, kp_id=verified_one, status="verified", evidence="验证"
            ),
            KnowledgeGap(
                user_id=user.id, goal_id=goal_id, kp_id=verified_two, status="verified", evidence="验证"
            ),
        ]
    )
    db.add(
        LearningExperiment(
            user_id=user.id,
            goal_id=goal_id,
            strategy="read",
            status="running",
            days=3,
            start_date=date.today(),
            end_date=date.today(),
        )
    )
    for index in range(4):
        _task(db, user, goal_id, priority=float(4 - index))
    db.commit()

    response = api("GET", "/api/goals/%d/cockpit" % goal_id, token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    # 覆盖度 0.9、时间匹配度 1.0、已验证漏洞 2 个：100×0.9×1.0 − min(15, 3×2) = 84
    assert body["readiness"]["score"] == 84
    assert body["readiness"]["level"] == "excellent"
    assert body["readiness"]["coverage"] == 0.9
    assert body["gap_count"] == 1
    assert body["verified_gap_count"] == 2
    assert body["experiment_count"] == 1
    assert [task["priority"] for task in body["critical_tasks"]] == [4.0, 3.0, 2.0]
    assert [risk["code"] for risk in body["risks"]] == ["knowledge"]
    assert body["risks"][0]["level"] == "high"


def test_cockpit_endpoint_requires_auth_and_valid_goal(api, auth):
    assert api("GET", "/api/goals/1/cockpit").status_code == 401
    response = api("GET", "/api/goals/99999/cockpit", token=auth["token"])
    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"


# --------------------------------------------------------------------------
# 知识漏洞地图
# --------------------------------------------------------------------------


def test_knowledge_graph_endpoint_reports_dependency_and_candidate(
    api, auth, goal, imported_points, db
):
    user = _tester(db)
    goal_id = goal["id"]
    leaf_id = _seed_candidate(db, user, goal_id, imported_points, "短对话")

    response = api("GET", "/api/goals/%d/knowledge-graph" % goal_id, token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["nodes"]) == len(imported_points)
    # 7 条父子依赖 + 4 条同级顺序依赖
    assert len(body["edges"]) == 11
    node = next(item for item in body["nodes"] if item["kp_id"] == leaf_id)
    assert node["parent"] == "听力"
    assert node["mastery"] == 0.2
    assert node["mistake_count"] == 2
    assert node["status"] == "candidate"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["kp_name"] == "短对话"
    assert "错题 2 道" in body["candidates"][0]["evidence"]
    assert body["verified"] == []
    assert body["fixed_count"] == 0


def test_gap_verification_uses_rule_engine_without_deepseek(
    api, auth, goal, imported_points, db, monkeypatch
):
    from app import llm as llm_module

    async def boom(*args, **kwargs):
        raise AssertionError("测试期间禁止调用真实 DeepSeek")

    monkeypatch.setattr(llm_module.llm, "chat", boom)
    monkeypatch.setattr(llm_module.llm, "chat_json", boom)

    user = _tester(db)
    goal_id = goal["id"]
    leaf_id = _seed_candidate(db, user, goal_id, imported_points, "短对话")
    gap_id = _candidate_gap_id(api, auth["token"], goal_id)

    verify = api("POST", "/api/gaps/%d/verify" % gap_id, token=auth["token"])

    assert verify.status_code == 200, verify.text
    quiz = verify.json()
    # 大模型不可用时必须回退到规则题或内置题库
    assert quiz["engine"] in {"rule", "bank"}
    assert len(quiz["questions"]) >= 1
    assert quiz["questions"][0]["kp_id"] == leaf_id

    stored = cache.get_json("quiz:%d:%s" % (user.id, quiz["quiz_id"]))
    assert stored is not None
    answers = [
        (item["answer_index"] + 1) % len(item["options"]) for item in stored["questions"]
    ]
    submit = api(
        "POST",
        "/api/gaps/%d/submit" % gap_id,
        token=auth["token"],
        json={"quiz_id": quiz["quiz_id"], "answers": answers},
    )

    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["gap"]["status"] == "verified"
    assert "确认存在漏洞" in body["gap"]["evidence"]
    assert body["result"]["correct"] == 0
    assert body["result"]["total"] == len(stored["questions"])
    assert body["repair_task_id"] is not None
    repair = db.get(Task, body["repair_task_id"])
    assert repair.type == "remedial"
    assert repair.kp_id == leaf_id
    assert repair.source == "gap"


def test_gap_verification_all_correct_marks_fixed(
    api, auth, goal, imported_points, db
):
    user = _tester(db)
    goal_id = goal["id"]
    _seed_candidate(db, user, goal_id, imported_points, "长对话")
    gap_id = _candidate_gap_id(api, auth["token"], goal_id)

    quiz = api("POST", "/api/gaps/%d/verify" % gap_id, token=auth["token"]).json()
    stored = cache.get_json("quiz:%d:%s" % (user.id, quiz["quiz_id"]))
    answers = [item["answer_index"] for item in stored["questions"]]
    submit = api(
        "POST",
        "/api/gaps/%d/submit" % gap_id,
        token=auth["token"],
        json={"quiz_id": quiz["quiz_id"], "answers": answers},
    )

    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["gap"]["status"] == "fixed"
    assert "验证题全部通过" in body["gap"]["evidence"]
    assert body["result"]["correct"] == body["result"]["total"] == len(stored["questions"])
    assert body["repair_task_id"] is None
    assert db.scalars(select(Task).where(Task.type == "remedial")).all() == []


def test_gap_verification_without_points_returns_400(
    api, auth, goal, imported_points, db
):
    user = _tester(db)
    empty = api("POST", "/api/goals", token=auth["token"], json=GOAL_PAYLOAD)
    assert empty.status_code == 201, empty.text
    empty_goal_id = empty.json()["id"]
    gap = KnowledgeGap(
        user_id=user.id,
        goal_id=empty_goal_id,
        kp_id=imported_points[0]["id"],
        status="candidate",
        evidence="人工记录",
    )
    db.add(gap)
    db.commit()

    response = api("POST", "/api/gaps/%d/verify" % gap.id, token=auth["token"])

    assert response.status_code == 400
    assert response.json()["detail"] == "还没有知识点，请先导入资料"


def test_gap_submit_with_expired_quiz_returns_400(
    api, auth, goal, imported_points, db
):
    user = _tester(db)
    goal_id = goal["id"]
    _seed_candidate(db, user, goal_id, imported_points, "短对话")
    gap_id = _candidate_gap_id(api, auth["token"], goal_id)

    response = api(
        "POST",
        "/api/gaps/%d/submit" % gap_id,
        token=auth["token"],
        json={"quiz_id": "not-exists", "answers": [0]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "题目已过期，请重新生成"


def test_gap_endpoints_reject_unknown_gap(api, auth):
    token = auth["token"]
    assert api("POST", "/api/gaps/99999/verify", token=token).status_code == 404
    response = api(
        "POST",
        "/api/gaps/99999/submit",
        token=token,
        json={"quiz_id": "x", "answers": []},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "漏洞记录不存在"


# --------------------------------------------------------------------------
# 未来模拟实验室
# --------------------------------------------------------------------------


def test_simulate_endpoint_returns_four_strategy_plans(api, auth, goal, imported_points):
    response = api("GET", "/api/goals/%d/simulate" % goal["id"], token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert [plan["key"] for plan in body["plans"]] == [
        "keep",
        "more_time",
        "repair",
        "combo",
    ]
    assert body["days_left"] == 40
    assert body["current_mastery"] == 0.0
    assert 0.7 <= body["target_mastery"] <= 0.9
    assert "不构成成绩保证" in body["uncertainty"]
    assert body["recommendation"].startswith("推荐「")
    for plan in body["plans"]:
        assert plan["low"] <= plan["projected_mastery"] <= plan["high"]
        assert plan["assumptions"]


def test_simulate_endpoint_without_points_returns_hint(api, auth):
    created = api("POST", "/api/goals", token=auth["token"], json=GOAL_PAYLOAD)
    assert created.status_code == 201, created.text
    goal_id = created.json()["id"]

    response = api("GET", "/api/goals/%d/simulate" % goal_id, token=auth["token"])

    assert response.status_code == 200
    body = response.json()
    assert body["plans"] == []
    assert body["recommendation"] == "先导入知识点再模拟。"


def test_simulate_endpoint_requires_auth_and_valid_goal(api, auth):
    assert api("GET", "/api/goals/1/simulate").status_code == 401
    assert api("GET", "/api/goals/99999/simulate", token=auth["token"]).status_code == 404


# --------------------------------------------------------------------------
# 风险救援中心
# --------------------------------------------------------------------------


def test_risks_endpoint_reports_knowledge_and_strategy_without_data(
    api, auth, goal, imported_points
):
    response = api("GET", "/api/goals/%d/risks" % goal["id"], token=auth["token"])

    assert response.status_code == 200, response.text
    risks = response.json()
    # 3 个一级知识点（权重 1.5）掌握度为 0，触发高等级知识风险；
    # 同时没有错题与已验证漏洞，命中策略风险。
    assert [risk["code"] for risk in risks] == ["knowledge", "strategy"]
    assert risks[0]["level"] == "high"
    assert "高权重薄弱知识点 3 个" in risks[0]["reason"]
    assert risks[1]["level"] == "low"
    assert risks[1]["action"] == "去策略实验室"


def test_risks_resolve_executes_each_rescue_action(
    api, auth, goal, imported_points, db
):
    user = _tester(db)
    goal_id = goal["id"]
    token = auth["token"]
    _task(db, user, goal_id, priority=5.0)
    _task(db, user, goal_id, priority=1.0)
    db.commit()

    time_resp = api("POST", "/api/goals/%d/risks/time/resolve" % goal_id, token=token)
    assert time_resp.status_code == 200, time_resp.text
    time_body = time_resp.json()
    assert "已降载" in time_body["message"]
    assert time_body["changes"][0]["kind"] == "defer"
    assert isinstance(time_body["before"], dict)
    assert isinstance(time_body["after"], dict)

    knowledge_resp = api(
        "POST", "/api/goals/%d/risks/knowledge/resolve" % goal_id, token=token
    )
    assert knowledge_resp.status_code == 200, knowledge_resp.text
    knowledge_body = knowledge_resp.json()
    assert knowledge_body["message"] == "已生成 2 个漏洞修复任务，完成后请做验证题确认。"
    assert len(knowledge_body["changes"]) == 2

    memory_resp = api(
        "POST", "/api/goals/%d/risks/memory/resolve" % goal_id, token=token
    )
    assert memory_resp.status_code == 200, memory_resp.text
    memory_body = memory_resp.json()
    assert memory_body["message"] == "已插入 15 分钟复习任务。"
    assert memory_body["changes"][0]["kind"] == "review"

    fallback_resp = api(
        "POST", "/api/goals/%d/risks/strategy/resolve" % goal_id, token=token
    )
    assert fallback_resp.status_code == 200, fallback_resp.text
    assert "策略实验" in fallback_resp.json()["message"]

    repair_tasks = db.scalars(select(Task).where(Task.type == "remedial")).all()
    assert len(repair_tasks) == 2
    review_tasks = db.scalars(select(Task).where(Task.type == "review")).all()
    assert len(review_tasks) == 1
    triggers = {log.trigger for log in db.scalars(select(ReplanLog)).all()}
    assert "risk_rest" in triggers
    assert "risk_knowledge" in triggers


def test_risks_endpoint_requires_auth_and_valid_goal(api, auth):
    assert api("GET", "/api/goals/1/risks").status_code == 401
    assert api("GET", "/api/goals/99999/risks", token=auth["token"]).status_code == 404


# --------------------------------------------------------------------------
# 策略实验室
# --------------------------------------------------------------------------


def test_experiment_lifecycle_via_api(api, auth, goal):
    token = auth["token"]
    goal_id = goal["id"]

    listing = api("GET", "/api/goals/%d/experiments" % goal_id, token=token)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"] == []
    assert listing.json()["ranking"] == []
    assert len(listing.json()["strategies"]) == 4

    created = api(
        "POST",
        "/api/goals/%d/experiments" % goal_id,
        token=token,
        json={"strategy": "flashcard", "days": 3},
    )
    assert created.status_code == 201, created.text
    experiment = created.json()
    assert experiment["status"] == "running"
    assert experiment["strategy"] == "flashcard"
    assert experiment["days"] == 3
    assert experiment["start_date"] == date.today().isoformat()
    assert experiment["end_date"] == (date.today() + timedelta(days=2)).isoformat()
    assert experiment["gain"] == 0.0

    finished = api(
        "POST",
        "/api/experiments/%d/finish" % experiment["id"],
        token=token,
        json={"immediate_score": 82, "delayed_score": 70, "note": "闪卡三日实验"},
    )
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "finished"
    assert body["immediate_score"] == 82
    assert body["delayed_score"] == 70
    assert body["note"] == "闪卡三日实验"
    assert body["gain"] == 0.0

    # 重复结束应保持已完成状态且不报错
    again = api(
        "POST",
        "/api/experiments/%d/finish" % experiment["id"],
        token=token,
        json={"immediate_score": 10, "delayed_score": 10},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "finished"
    assert again.json()["immediate_score"] == 82

    ranking = api("GET", "/api/goals/%d/experiments" % goal_id, token=token).json()
    assert len(ranking["items"]) == 1
    assert ranking["ranking"] == [
        {"strategy": "flashcard", "label": "闪卡记忆", "avg_gain": 0.0, "experiments": 1}
    ]


def test_experiment_create_and_finish_validation(api, auth, goal):
    token = auth["token"]
    goal_id = goal["id"]

    invalid_strategy = api(
        "POST",
        "/api/goals/%d/experiments" % goal_id,
        token=token,
        json={"strategy": "sleep", "days": 3},
    )
    assert invalid_strategy.status_code == 400
    assert "read / practice / flashcard / ai_tutor" in invalid_strategy.json()["detail"]

    invalid_days = api(
        "POST",
        "/api/goals/%d/experiments" % goal_id,
        token=token,
        json={"strategy": "read", "days": 0},
    )
    assert invalid_days.status_code == 422

    invalid_score = api(
        "POST",
        "/api/experiments/1/finish",
        token=token,
        json={"immediate_score": 101, "delayed_score": 60},
    )
    assert invalid_score.status_code == 422

    unknown = api(
        "POST",
        "/api/experiments/99999/finish",
        token=token,
        json={"immediate_score": 80, "delayed_score": 70},
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "实验不存在"


# --------------------------------------------------------------------------
# AI 学习数字孪生
# --------------------------------------------------------------------------


def test_twin_endpoint_returns_state_portrait(api, auth, goal, imported_points):
    response = api("GET", "/api/goals/%d/twin" % goal["id"], token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["knowledge_matrix"]) == len(imported_points)
    child = next(item for item in body["knowledge_matrix"] if item["name"] == "短对话")
    assert child["parent"] == "听力"
    assert [item["category"] for item in body["mistake_distribution"]] == [
        "concept",
        "method",
        "careless",
        "time",
    ]
    assert all(item["count"] == 0 for item in body["mistake_distribution"])
    assert len(body["behavior_trend"]) == 8
    assert body["strategy_ranking"] == []


def test_twin_endpoint_requires_auth_and_valid_goal(api, auth):
    assert api("GET", "/api/goals/1/twin").status_code == 401
    response = api("GET", "/api/goals/99999/twin", token=auth["token"])
    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"