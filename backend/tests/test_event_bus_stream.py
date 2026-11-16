"""事件总线（文档 7.5）与 P06/P15 流式接口的测试。"""

import json

import pytest
from sqlalchemy import select

from app.models import EventLog, KnowledgePoint
from app.services import event_bus


# ---------------------------------------------------------------- 路由决策
def test_quiz_event_routes_to_four_handlers():
    decision = event_bus.route("quiz_answered", {"score": 80})
    assert decision["handlers"] == ["mastery_service", "flashcards", "diagnoser", "planner"]
    assert decision["auto"] is True
    assert decision["needs_confirmation"] is False


def test_risk_event_requires_confirmation():
    decision = event_bus.route("risk_detected", {})
    assert decision["needs_confirmation"] is True
    assert decision["auto"] is False
    assert "risk_rescue" in decision["handlers"]


def test_internal_event_names_are_aliased():
    assert event_bus.route("answer")["route_type"] == "quiz_answered"
    assert event_bus.route("material")["route_type"] == "material_uploaded"
    assert event_bus.route("task_skip")["route_type"] == "task_overdue"


def test_unknown_event_falls_back_to_coach():
    decision = event_bus.route("something_new")
    assert decision["handlers"] == ["coach"]
    assert decision["auto"] is True


def test_extra_handler_can_extend_decision():
    event_bus.register("quiz_answered")(lambda payload: {"extra": payload.get("score", 0) * 2})
    decision = event_bus.route("quiz_answered", {"score": 10})
    assert decision["extra"] == 20
    event_bus.EXTRA_HANDLERS.clear()


# ---------------------------------------------------------------- 落库与幂等
def test_publish_writes_event_log_with_handled_by(db, db_user_goal):
    user, goal = db_user_goal
    result = event_bus.publish(db, "fatigue_high", user.id, goal.id, {"index": 72})
    db.commit()

    assert result["event_id"] and result["route_type"] == "fatigue_high"
    log = db.scalars(select(EventLog)).one()
    assert log.type == "fatigue_high"
    assert "rest_station" in log.handled_by
    assert log.user_id == user.id


def test_publish_is_append_only(db, db_user_goal):
    user, goal = db_user_goal
    ids = {
        event_bus.publish(db, "task_overdue", user.id, goal.id, {"task_id": index})["event_id"]
        for index in range(3)
    }
    db.commit()
    assert len(ids) == 3
    assert len(db.scalars(select(EventLog)).all()) == 3


# ---------------------------------------------------------------- API
def test_events_routes_endpoint_lists_routing_table(api, auth):
    body = api("GET", "/api/events/routes", token=auth["token"]).json()
    types = {item["type"] for item in body["items"]}
    assert {"quiz_answered", "task_overdue", "risk_detected"} <= types
    risk = next(item for item in body["items"] if item["type"] == "risk_detected")
    assert risk["needs_confirmation"] is True


def test_events_recent_endpoint_returns_user_events(api, auth, db, goal):
    user_id = auth["user"]["id"]
    event_bus.publish(db, "quiz_answered", user_id, goal["id"], {"score": 90})
    db.commit()

    body = api("GET", "/api/events/recent", token=auth["token"]).json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "quiz_answered"
    assert "diagnoser" in body["items"][0]["handled_by"]


# ---------------------------------------------------------------- SSE
def test_socratic_stream_falls_back_without_llm(api, auth, goal, db):
    user = auth["user"]
    point = KnowledgePoint(goal_id=goal["id"], name="从句", weight=1.0)
    db.add(point)
    db.commit()

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/socratic/stream",
        token=auth["token"],
        json={"kp_id": point.id, "message": "从句是什么", "level": "concept"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: stage" in text
    assert "event: fallback" in text
    assert "从句" in text


def test_socratic_stream_rejects_foreign_knowledge_point(api, auth, goal, db):
    point = KnowledgePoint(goal_id=goal["id"] + 100, name="别的目标", weight=1.0)
    db.add(point)
    db.commit()

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/socratic/stream",
        token=auth["token"],
        json={"kp_id": point.id, "message": "", "level": "direction"},
    )
    assert response.status_code == 404


def test_voice_stream_falls_back_without_llm(api, auth, goal):
    response = api(
        "POST",
        "/api/voice/ask/stream",
        token=auth["token"],
        json={"question": "今天学什么"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: fallback" in text or "event: result" in text
    assert "没听清" in text or "今天" in text
