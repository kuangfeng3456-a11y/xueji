"""反向教学三件套：费曼讲解、反向判卷、错误免疫。

这些用例全部在关闭大模型的条件下跑，验证的是「判定不依赖模型」这一核心承诺：
要点清单、错误步骤、诱饵选项都由服务端预置，模型不可用时也能判分。
"""

from app.models import Mistake


def _start_feynman(api, token, goal_id, kp_id):
    response = api(
        "POST",
        "/api/teaching/feynman/start",
        token=token,
        json={"goal_id": goal_id, "kp_id": kp_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_feynman_start_uses_graph_points_and_hides_them(api, auth, goal, imported_points):
    point = imported_points[0]
    body = _start_feynman(api, auth["token"], goal["id"], point["id"])

    assert body["kp_name"] == point["name"]
    # 无模型时回落到「图谱子节点」，知识点下有三个子节点
    assert body["engine"] in {"graph", "rule"}
    assert "points" not in body, "要点清单不能下发给前端，否则照着念就不算讲解"
    assert body["min_chars"] >= 30


def test_feynman_submit_scores_coverage_deterministically(api, auth, goal, imported_points):
    token = auth["token"]
    started = _start_feynman(api, token, goal["id"], imported_points[0]["id"])

    speech = (
        "听力这部分要抓短对话里的语气和场景，长对话要听清楚人物关系，"
        "遇到数字先记下来。做题前先看选项，预判会问什么。"
    )
    response = api(
        "POST",
        "/api/teaching/feynman/submit",
        token=token,
        json={"session_id": started["session_id"], "speech": speech},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["engine"] == "rule"
    assert 0 < body["coverage"] <= 1
    assert body["covered"], "提到了子节点名称，应有命中"
    assert all("hint" in item for item in body["missed"])
    assert body["verdict"]

    again = api(
        "POST",
        "/api/teaching/feynman/submit",
        token=token,
        json={"session_id": started["session_id"], "speech": speech},
    )
    assert again.status_code == 400
    assert "已经核对过" in again.json()["detail"]


def test_feynman_rejects_too_short_speech(api, auth, goal, imported_points):
    token = auth["token"]
    started = _start_feynman(api, token, goal["id"], imported_points[0]["id"])
    response = api(
        "POST",
        "/api/teaching/feynman/submit",
        token=token,
        json={"session_id": started["session_id"], "speech": "就是那个东西"},
    )
    assert response.status_code == 400
    assert "太短" in response.json()["detail"]


def test_feynman_profile_counts_attempts(api, auth, goal, imported_points):
    token = auth["token"]
    started = _start_feynman(api, token, goal["id"], imported_points[0]["id"])
    api(
        "POST",
        "/api/teaching/feynman/submit",
        token=token,
        json={
            "session_id": started["session_id"],
            "speech": "短对话要注意语气和场景，长对话要听清人物关系，听力篇章先抓主旨大意再看细节。",
        },
    )
    profile = api("GET", f"/api/teaching/feynman/profile?goal_id={goal['id']}", token=token).json()
    assert profile["attempts"] == 1
    assert profile["items"][0]["sessions"] == 1
    assert profile["avg_coverage"] is not None


def test_reverse_grade_breakdown_is_rule_based(api, auth, goal, imported_points):
    token = auth["token"]
    started = api(
        "POST",
        "/api/teaching/reverse/start",
        token=token,
        json={"goal_id": goal["id"], "kp_id": imported_points[0]["id"], "cause": "概念不清"},
    ).json()

    assert started["engine"] == "rule", "无模型时使用规则题"
    assert len(started["steps"]) >= 3
    assert "error_step" not in started, "错误位置不能下发"
    assert "correct_step" not in started

    graded = api(
        "POST",
        "/api/teaching/reverse/grade",
        token=token,
        json={
            "task_id": started["task_id"],
            "picked_step": 3,
            "picked_type": "概念不清",
            "fix_text": "这里没写前提条件，也没有举反例说明适用范围。",
        },
    )
    assert graded.status_code == 200, graded.text
    body = graded.json()
    # 定位 45 + 错因 30 + 修正（3 个关键词全提到）25 = 100
    assert body["breakdown"]["position"]["points"] == 45
    assert body["breakdown"]["type"]["points"] == 30
    assert body["breakdown"]["fix"]["points"] == 25
    assert body["score"] == 100
    assert body["truth"]["error_step"] == 3
    assert body["truth"]["key_terms"]

    again = api(
        "POST",
        "/api/teaching/reverse/grade",
        token=token,
        json={"task_id": started["task_id"], "picked_step": 3, "picked_type": "概念不清", "fix_text": "改了"},
    )
    assert again.status_code == 400


def test_reverse_wrong_position_scores_zero_on_position(api, auth, goal, imported_points):
    token = auth["token"]
    started = api(
        "POST",
        "/api/teaching/reverse/start",
        token=token,
        json={"goal_id": goal["id"], "kp_id": imported_points[0]["id"], "cause": "粗心"},
    ).json()

    body = api(
        "POST",
        "/api/teaching/reverse/grade",
        token=token,
        json={"task_id": started["task_id"], "picked_step": 1, "picked_type": "粗心", "fix_text": ""},
    ).json()
    assert body["breakdown"]["position"]["points"] == 0
    assert body["breakdown"]["type"]["points"] == 30
    assert body["score"] == 30
    assert body["tier"] == "weak"


def test_reverse_profile_crosses_own_causes(api, auth, goal, imported_points, db):
    token = auth["token"]
    user_id = auth["user"]["id"]
    kp = imported_points[0]
    for _ in range(3):
        db.add(
            Mistake(
                user_id=user_id,
                goal_id=goal["id"],
                kp_id=kp["id"],
                question="粗心错的题",
                user_answer="A",
                correct_answer="B",
                category="careless",
                category_label="粗心",
            )
        )
    db.commit()

    started = api(
        "POST",
        "/api/teaching/reverse/start",
        token=token,
        json={"goal_id": goal["id"], "kp_id": kp["id"], "cause": "粗心"},
    ).json()
    api(
        "POST",
        "/api/teaching/reverse/grade",
        token=token,
        json={"task_id": started["task_id"], "picked_step": 3, "picked_type": "概念不清", "fix_text": ""},
    )

    profile = api("GET", f"/api/teaching/reverse/profile?goal_id={goal['id']}", token=token).json()
    assert profile["attempts"] == 1
    assert profile["own_total"] == 3
    assert profile["sample_state"] == "exploratory", "少于 3 次判卷只给探索性结论"
    assert profile["by_type"][0]["cause"] == "概念不清"


def test_immune_fingerprint_needs_two_same_errors(api, auth, goal, imported_points, db):
    token = auth["token"]
    user_id = auth["user"]["id"]
    kp = imported_points[1]
    for _ in range(2):
        db.add(
            Mistake(
                user_id=user_id,
                goal_id=goal["id"],
                kp_id=kp["id"],
                question="阅读题",
                user_answer="C",
                correct_answer="A",
                category="concept",
                category_label="概念不清",
            )
        )
    db.commit()

    stats = api("GET", f"/api/teaching/immune/fingerprints?goal_id={goal['id']}", token=token).json()
    assert stats["total"] == 1
    item = stats["items"][0]
    assert item["count"] == 2
    assert item["status"] == "naive"

    drill = api(
        "POST",
        "/api/teaching/immune/drill",
        token=token,
        json={"goal_id": goal["id"], "fingerprint": item["fingerprint"]},
    ).json()
    assert drill["engine"] == "replay", "无模型时把用户原题重演一遍"
    assert len(drill["options"]) == 4
    assert "trap_key" not in drill, "诱饵与正确答案都不能下发"
    assert "correct_key" not in drill

    answered = api(
        "POST",
        "/api/teaching/immune/answer",
        token=token,
        json={"drill_id": drill["drill_id"], "picked": "B"},
    ).json()
    assert answered["outcome"] == "relapse"
    assert answered["trap_key"] == "B"
    assert answered["status_label"] == "复发预警"

    repeated = api(
        "POST",
        "/api/teaching/immune/answer",
        token=token,
        json={"drill_id": drill["drill_id"], "picked": "A"},
    )
    assert repeated.status_code == 400


def test_immune_guard_accumulates(api, auth, goal, imported_points, db):
    token = auth["token"]
    user_id = auth["user"]["id"]
    kp = imported_points[1]
    for _ in range(2):
        db.add(
            Mistake(
                user_id=user_id,
                goal_id=goal["id"],
                kp_id=kp["id"],
                question="阅读题",
                user_answer="C",
                correct_answer="A",
                category="concept",
                category_label="概念不清",
            )
        )
    db.commit()

    fingerprint = api(
        "GET", f"/api/teaching/immune/fingerprints?goal_id={goal['id']}", token=token
    ).json()["items"][0]["fingerprint"]

    last = None
    for _ in range(3):
        drill = api(
            "POST",
            "/api/teaching/immune/drill",
            token=token,
            json={"goal_id": goal["id"], "fingerprint": fingerprint},
        ).json()
        last = api(
            "POST",
            "/api/teaching/immune/answer",
            token=token,
            json={"drill_id": drill["drill_id"], "picked": "A"},
        ).json()
        assert last["outcome"] == "guard"

    assert last["guards"] == 3
    assert last["status"] == "immune"

    stats = api("GET", f"/api/teaching/immune/fingerprints?goal_id={goal['id']}", token=token).json()
    assert stats["immune"] == 1
    profile = api("GET", f"/api/teaching/immune/profile?goal_id={goal['id']}", token=token).json()
    assert profile["answered"] == 3
    assert profile["guard_rate"] == 1.0


def test_immune_drill_without_mistakes_is_refused(api, auth, goal, imported_points):
    response = api(
        "POST",
        "/api/teaching/immune/drill",
        token=auth["token"],
        json={"goal_id": goal["id"]},
    )
    assert response.status_code == 400
    assert "错题" in response.json()["detail"]


def test_teaching_endpoints_require_goal_ownership(api, auth):
    response = api(
        "POST",
        "/api/teaching/feynman/start",
        token=auth["token"],
        json={"goal_id": 9999},
    )
    assert response.status_code == 404
