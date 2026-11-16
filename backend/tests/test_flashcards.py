"""闪卡复习模块单元测试：卡片生成、到期判定、排序与复习调度。"""

from datetime import date, timedelta

import pytest

from app.models import Goal, KnowledgePoint, Mastery
from app.services.flashcards import _goal_points, build_deck, review_card


def _tree(db, goal):
    parent = KnowledgePoint(goal_id=goal.id, name="阅读", weight=2.0)
    db.add(parent)
    db.flush()
    child_a = KnowledgePoint(goal_id=goal.id, name="选词填空", weight=1.5, parent_id=parent.id)
    child_b = KnowledgePoint(goal_id=goal.id, name="仔细阅读", weight=1.0, parent_id=parent.id)
    db.add_all([child_a, child_b])
    db.flush()
    return parent, child_a, child_b


def _point(db, goal, name, weight=1.0):
    point = KnowledgePoint(goal_id=goal.id, name=name, weight=weight)
    db.add(point)
    db.flush()
    return point


def _mastery(db, user, point, value, next_review_at=None):
    record = Mastery(
        user_id=user.id,
        kp_id=point.id,
        value=value,
        review_stage=1,
        next_review_at=next_review_at,
    )
    db.add(record)
    db.flush()
    return record


# --------------------------------------------------------------------------
# _goal_points
# --------------------------------------------------------------------------


def test_goal_points_returns_leaf_knowledge_points(db, db_user_goal):
    user, goal = db_user_goal
    parent, child_a, child_b = _tree(db, goal)
    db.commit()

    points = _goal_points(db, goal.id)

    assert {point.id for point in points} == {child_a.id, child_b.id}
    assert parent.id not in {point.id for point in points}


def test_goal_points_falls_back_for_self_referencing_point(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "循环知识点")
    point.parent_id = point.id
    db.commit()

    points = _goal_points(db, goal.id)

    assert [item.id for item in points] == [point.id]


def test_goal_points_without_points_is_empty(db, db_user_goal):
    user, goal = db_user_goal
    assert _goal_points(db, goal.id) == []


# --------------------------------------------------------------------------
# build_deck
# --------------------------------------------------------------------------


def test_build_deck_without_points_returns_empty_deck(db, db_user_goal):
    user, goal = db_user_goal
    deck = build_deck(db, user.id, goal.id)

    assert deck["cards"] == []
    assert deck["total"] == 0
    assert deck["due_count"] == 0
    assert 0.8 <= deck["target_retention"] <= 0.95
    assert deck["phase"] in {"foundation", "reinforce", "sprint", "final"}
    assert deck["phase_label"]


def test_build_deck_marks_unseen_cards_due(db, db_user_goal):
    user, goal = db_user_goal
    _tree(db, goal)
    db.commit()

    deck = build_deck(db, user.id, goal.id)
    cards = {card["kp_name"]: card for card in deck["cards"]}

    assert deck["total"] == 2
    assert deck["due_count"] == 2
    assert cards["选词填空"]["parent"] == "阅读"
    assert cards["选词填空"]["weight"] == 1.5
    assert cards["选词填空"]["mastery"] == 0.0
    assert cards["选词填空"]["next_review_at"] is None
    assert cards["选词填空"]["due"] is True
    assert cards["选词填空"]["reason"] == "遗忘曲线到期"


def test_build_deck_reasons_follow_mastery_level(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    low = _point(db, goal, "基础")
    mid = _point(db, goal, "巩固")
    high = _point(db, goal, "熟练")
    _mastery(db, user, low, 0.2, today + timedelta(days=3))
    _mastery(db, user, mid, 0.5, today + timedelta(days=3))
    _mastery(db, user, high, 0.8, today + timedelta(days=3))
    db.commit()

    deck = build_deck(db, user.id, goal.id, today=today)
    cards = {card["kp_name"]: card for card in deck["cards"]}

    assert deck["due_count"] == 0
    assert all(card["due"] is False for card in cards.values())
    assert cards["基础"]["reason"] == "掌握度偏低，优先补基础"
    assert cards["巩固"]["reason"] == "待巩固"
    assert cards["熟练"]["reason"] == "保持手感"
    assert cards["熟练"]["mastery"] == 0.8


def test_build_deck_treats_today_and_missing_next_review_as_due(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    due_today = _point(db, goal, "今日到期")
    never_scheduled = _point(db, goal, "未排期")
    _mastery(db, user, due_today, 0.9, today)
    _mastery(db, user, never_scheduled, 0.9, None)
    db.commit()

    deck = build_deck(db, user.id, goal.id, today=today)
    cards = {card["kp_name"]: card for card in deck["cards"]}

    assert cards["今日到期"]["due"] is True
    assert cards["今日到期"]["reason"] == "遗忘曲线到期"
    assert cards["未排期"]["due"] is True


def test_build_deck_sorts_due_then_mastery_then_weight(db, db_user_goal):
    user, goal = db_user_goal
    today = date.today()
    due_point = _point(db, goal, "到期", weight=0.5)
    low_point = _point(db, goal, "低掌握", weight=1.0)
    heavy_point = _point(db, goal, "高权重", weight=3.0)
    light_point = _point(db, goal, "低权重", weight=1.0)
    _mastery(db, user, low_point, 0.1, today + timedelta(days=2))
    _mastery(db, user, heavy_point, 0.5, today + timedelta(days=2))
    _mastery(db, user, light_point, 0.5, today + timedelta(days=2))
    db.commit()

    deck = build_deck(db, user.id, goal.id, today=today)

    assert [card["kp_name"] for card in deck["cards"]] == [
        "到期",
        "低掌握",
        "高权重",
        "低权重",
    ]


def test_build_deck_limit_truncates_cards_but_not_counts(db, db_user_goal):
    user, goal = db_user_goal
    for index in range(5):
        _point(db, goal, f"知识点{index}", weight=1.0 + index)
    db.commit()

    deck = build_deck(db, user.id, goal.id, limit=2)

    assert len(deck["cards"]) == 2
    assert deck["total"] == 5
    assert deck["due_count"] == 5


# --------------------------------------------------------------------------
# review_card
# --------------------------------------------------------------------------


def test_review_card_rejects_unknown_knowledge_point(db, db_user_goal):
    user, goal = db_user_goal
    with pytest.raises(ValueError, match="知识点不存在"):
        review_card(db, user.id, goal.id, 99999, True)


def test_review_card_rejects_point_belonging_to_another_goal(db, db_user_goal):
    user, goal = db_user_goal
    other_goal = Goal(
        user_id=user.id,
        exam_name="另一个目标",
        exam_date=date.today() + timedelta(days=20),
        daily_minutes=60,
    )
    db.add(other_goal)
    db.flush()
    foreign_point = _point(db, other_goal, "外部知识点")
    db.commit()

    with pytest.raises(ValueError, match="知识点不存在"):
        review_card(db, user.id, goal.id, foreign_point.id, True)


def test_review_card_remembered_updates_mastery_and_schedule(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "听力")
    db.commit()
    today = date.today()

    result = review_card(db, user.id, goal.id, point.id, True)

    assert result["kp_id"] == point.id
    assert result["mastery"] == 0.08
    assert result["stage"] == 1
    assert result["next_review_at"] == today + timedelta(days=2)
    assert result["remaining_due"] == 0

    deck = build_deck(db, user.id, goal.id, today=today)
    assert deck["due_count"] == 0
    assert deck["cards"][0]["due"] is False
    assert deck["cards"][0]["reason"] == "掌握度偏低，优先补基础"


def test_review_card_forgotten_resets_stage_and_counts_remaining_due(db, db_user_goal):
    user, goal = db_user_goal
    reviewed = _point(db, goal, "已复习")
    pending = _point(db, goal, "待复习")
    db.commit()
    today = date.today()

    first = review_card(db, user.id, goal.id, reviewed.id, True)
    assert first["mastery"] == 0.08
    assert first["stage"] == 1
    assert first["remaining_due"] == 1

    second = review_card(db, user.id, goal.id, reviewed.id, False)
    assert second["mastery"] == 0.0957
    assert second["stage"] == 0
    assert second["next_review_at"] == today + timedelta(days=1)
    assert second["remaining_due"] == 1


# --------------------------------------------------------------------------
# API：/goals/{id}/flashcards
# --------------------------------------------------------------------------


def test_flashcards_endpoint_returns_empty_deck(api, auth, goal):
    response = api("GET", f"/api/goals/{goal['id']}/flashcards", token=auth["token"])

    assert response.status_code == 200, response.text
    assert response.json() == {"cards": [], "total": 0, "due_count": 0}


def test_flashcards_endpoint_builds_deck_from_imported_points(api, auth, goal, imported_points):
    response = api("GET", f"/api/goals/{goal['id']}/flashcards", token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 7
    assert body["due_count"] == 7
    assert len(body["cards"]) == 7
    assert all(card["due"] is True for card in body["cards"])
    assert all(card["reason"] == "遗忘曲线到期" for card in body["cards"])
    parents = {card["parent"] for card in body["cards"]}
    assert parents == {"听力", "阅读", "写作"}

    limited = api(
        "GET",
        f"/api/goals/{goal['id']}/flashcards",
        token=auth["token"],
        params={"limit": 2},
    )
    assert limited.status_code == 200
    assert len(limited.json()["cards"]) == 2
    assert limited.json()["total"] == 7


def test_flashcards_endpoint_validates_limit(api, auth, goal):
    token = auth["token"]
    for invalid in (0, 61):
        response = api(
            "GET",
            f"/api/goals/{goal['id']}/flashcards",
            token=token,
            params={"limit": invalid},
        )
        assert response.status_code == 422


def test_flashcards_review_endpoint_updates_schedule(api, auth, goal, imported_points):
    token = auth["token"]
    deck = api("GET", f"/api/goals/{goal['id']}/flashcards", token=token).json()
    target = deck["cards"][0]

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/{target['kp_id']}/review",
        token=token,
        json={"remembered": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kp_id"] == target["kp_id"]
    assert body["mastery"] == 0.08
    assert body["stage"] == 1
    assert body["next_review_at"] == (date.today() + timedelta(days=2)).isoformat()
    assert body["remaining_due"] == 6

    updated = api("GET", f"/api/goals/{goal['id']}/flashcards", token=token).json()
    assert updated["due_count"] == 6
    reviewed = [card for card in updated["cards"] if card["kp_id"] == target["kp_id"]][0]
    assert reviewed["due"] is False
    assert reviewed["mastery"] == 0.08
    assert reviewed["reason"] == "掌握度偏低，优先补基础"


def test_flashcards_review_endpoint_forgotten(api, auth, goal, imported_points):
    token = auth["token"]
    deck = api("GET", f"/api/goals/{goal['id']}/flashcards", token=token).json()
    kp_id = deck["cards"][0]["kp_id"]

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/{kp_id}/review",
        token=token,
        json={"remembered": False},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mastery"] == 0.08
    assert body["stage"] == 0
    assert body["next_review_at"] == (date.today() + timedelta(days=1)).isoformat()
    assert body["remaining_due"] == 6


def test_flashcards_review_endpoint_rejects_unknown_point(api, auth, goal):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/flashcards/99999/review",
        token=auth["token"],
        json={"remembered": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "知识点不存在"


def test_flashcards_endpoints_require_authentication(api, goal):
    assert api("GET", f"/api/goals/{goal['id']}/flashcards").status_code == 401
    assert (
        api(
            "POST",
            f"/api/goals/{goal['id']}/flashcards/1/review",
            json={"remembered": True},
        ).status_code
        == 401
    )


def test_flashcards_endpoint_rejects_unknown_goal(api, auth):
    response = api("GET", "/api/goals/99999/flashcards", token=auth["token"])
    assert response.status_code == 404
