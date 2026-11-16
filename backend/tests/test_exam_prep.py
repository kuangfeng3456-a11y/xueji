"""备考方案：阶段划分、每日三段课表、知识网络、真实视频课程与阶段模考。

这些用例验证三件事：
1. 排期与判定不经过模型（关掉大模型也能出完整课表）；
2. 内容来自真实数据（知识点、依赖关系来自数据库，不预置示例内容）；
3. 越权访问被拒绝。
"""

from app.models import ExamPrepDay, ExamPrepStage


def _plan(api, token, goal_id):
    response = api("GET", f"/api/goals/{goal_id}/exam-prep", token=token)
    assert response.status_code == 200, response.text
    return response.json()


def test_plan_splits_days_into_four_phases(api, auth, goal, imported_points):
    body = _plan(api, auth["token"], goal["id"])

    phases = [stage["phase"] for stage in body["stages"]]
    assert phases == ["foundation", "reinforce", "sprint", "final"], phases

    total = sum(stage["day_count"] for stage in body["stages"])
    assert total == body["totals"]["days"] == 40, "四阶段天数之和应等于总天数"

    # 阶段按时间递增、互不重叠
    for earlier, later in zip(body["stages"], body["stages"][1:]):
        assert earlier["end_date"] < later["start_date"]

    # 每个阶段都有目标保持率与配比（来自文档 5.5 阶段状态机）
    for stage in body["stages"]:
        assert 0 < stage["target_retention"] <= 1
        assert stage["ratio"]


def test_every_day_has_three_slots_with_knowledge_points(api, auth, goal, imported_points):
    body = _plan(api, auth["token"], goal["id"])

    for day in body["days"]:
        assert len(day["slots"]) == 3, f"第 {day['day_index']} 天应有早中晚三段"
        labels = [slot["label"] for slot in day["slots"]]
        assert labels == ["上午", "下午", "晚上"], labels

        for slot in day["slots"]:
            assert slot["title"], "每个时段都要有明确的标题"
            assert slot["focus"], "每个时段都要说清楚干什么"
            assert slot["minutes"] > 0
            assert slot["kp_names"], f"第 {day['day_index']} 天 {slot['label']} 没有安排知识点"
            assert len(slot["kp_ids"]) == len(slot["kp_names"])


def test_slot_roles_cover_new_practice_and_review(api, auth, goal, imported_points):
    body = _plan(api, auth["token"], goal["id"])
    roles = [slot["role"] for slot in body["days"][0]["slots"]]
    assert roles == ["new", "practice", "review"], roles


def test_days_advance_through_curriculum_not_repeat(api, auth, goal, imported_points):
    """课表要逐日推进，而不是天天排同样的考点。"""
    body = _plan(api, auth["token"], goal["id"])
    first = body["days"][0]["slots"][0]["kp_names"]
    later = body["days"][2]["slots"][0]["kp_names"]
    assert first != later, "相邻几天的上午课不应完全相同"


def test_stage_exam_day_is_marked_in_the_last_day_of_each_phase(api, auth, goal, imported_points):
    body = _plan(api, auth["token"], goal["id"])

    exam_days = [day["day_index"] for day in body["days"] if day["has_stage_exam"]]
    assert exam_days, "每个阶段都应该有一天安排阶段模考"

    # 模考安排在晚上
    for day in body["days"]:
        if day["has_stage_exam"]:
            evening = day["slots"][-1]
            assert evening["slot"] == "evening"
            assert evening.get("is_stage_exam") is True


def test_day_detail_returns_real_network_and_knowledge_graph(api, auth, goal, imported_points):
    token = auth["token"]
    _plan(api, token, goal["id"])

    response = api("GET", f"/api/goals/{goal['id']}/exam-prep/day/1", token=token)
    assert response.status_code == 200, response.text
    day = response.json()

    assert len(day["slots"]) == 3
    for slot in day["slots"]:
        # 知识网络来自数据库里的真实依赖关系
        network = slot["network"]
        assert network["nodes"], "知识网络要有节点"
        assert network["edges"], "知识网络要有先修/易混淆关系"
        assert all(edge.get("label") in {"先修", "易混淆", "相关"} for edge in network["edges"])

        # 视频必须如实标注来源与可用性；搜不到就说搜不到，不能塞内置示例
        video = slot["video"]
        assert video["source"] == "bilibili"
        assert "available" in video
        assert "engine" in video
        if not video["available"]:
            assert video["items"] == [], "没有视频时 items 必须为空"
            assert video.get("detail")


def test_stage_exam_covers_multiple_knowledge_points(api, auth, goal, imported_points):
    token = auth["token"]
    body = _plan(api, token, goal["id"])
    stage = body["stages"][0]

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/exam-prep/stage-exam",
        token=token,
        json={"stage_id": stage["id"], "count": 4},
    )
    assert response.status_code == 200, response.text
    exam = response.json()

    assert exam["stage_id"] == stage["id"]
    assert len(exam["questions"]) == 4
    # 模考要覆盖多个考点，不能只考一个
    covered = {question.get("kp_id") for question in exam["questions"]}
    assert len(covered) >= 2, f"模考只覆盖了 {covered}"


def test_stage_exam_submit_records_score_on_stage(api, auth, goal, imported_points):
    token = auth["token"]
    body = _plan(api, token, goal["id"])
    stage = body["stages"][0]

    exam = api(
        "POST",
        f"/api/goals/{goal['id']}/exam-prep/stage-exam",
        token=token,
        json={"stage_id": stage["id"], "count": 3},
    ).json()
    answers = [0] * len(exam["questions"])

    result = api(
        "POST",
        f"/api/goals/{goal['id']}/exam-prep/stage-exam/submit",
        token=token,
        json={"quiz_id": exam["quiz_id"], "answers": answers},
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["total"] == len(answers)
    assert "passed" in payload
    assert payload["stage_id"] == stage["id"]

    # 成绩要落到阶段上，重新读方案能看到
    refreshed = _plan(api, token, goal["id"])
    stored = next(item for item in refreshed["stages"] if item["id"] == stage["id"])
    assert stored["exam_score"] == payload["score"]
    assert stored["exam_total"] == payload["total"]
    assert stored["status"] == "done"


def test_rebuild_replaces_previous_plan(api, auth, goal, imported_points):
    token = auth["token"]
    _plan(api, token, goal["id"])

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/exam-prep/build",
        token=token,
        json={"regenerate": True},
    )
    assert response.status_code == 200, response.text
    rebuilt = response.json()
    assert rebuilt["totals"]["days"] == 40
    # 重建后不能留下重复的阶段记录
    ids = [stage["id"] for stage in rebuilt["stages"]]
    assert len(ids) == len(set(ids))


def test_exam_prep_requires_goal_ownership(api, auth, goal, imported_points):
    other = api(
        "POST",
        "/api/goals",
        token=auth["token"],
        json={
            "exam_name": "别人的目标",
            "exam_date": "2027-01-01",
            "daily_minutes": 60,
        },
    ).json()

    response = api("GET", f"/api/goals/{other['id']}/exam-prep", token=auth["token"])
    # 同一个用户的目标可以访问：新目标还没导入资料，应给出可解释的 400 而不是 404
    assert response.status_code == 400, response.text
    assert "知识点" in response.text

    foreign = api(
        "POST",
        "/api/auth/register",
        json={"username": "other", "password": "secret123", "nickname": "别人"},
    ).json()
    denied = api("GET", f"/api/goals/{goal['id']}/exam-prep", token=foreign["access_token"])
    assert denied.status_code == 404


def test_plan_rows_are_persisted_not_computed_on_the_fly(api, auth, goal, imported_points, db):
    """课表要落库，刷新页面不会因为掌握度变化而丢掉整份方案。"""
    _plan(api, auth["token"], goal["id"])
    stages = db.query(ExamPrepStage).filter_by(goal_id=goal["id"]).all()
    days = db.query(ExamPrepDay).filter_by(goal_id=goal["id"]).all()
    assert len(stages) == 4
    assert len(days) == 40
    assert all(day.slots for day in days), "每天的时段都要落库"
