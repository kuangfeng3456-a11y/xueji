"""反事实 Why 与阶段目标保持率：数字必须能由规则复算。"""

from datetime import date, timedelta

from app.models import KnowledgePoint
from app.services.flashcards import build_deck
from app.services.rules import expected_gain, task_why, value_density


def test_task_why_exposes_recomputable_counterfactuals():
    why = task_why(
        weight=0.4,
        mastery=0.3,
        retention_now=0.8,
        uncertainty=0.12,
        days_left_count=20,
        kind="review",
        minutes=20,
        gate=1.0,
        rank=1,
        stability=7.0,
    )
    gain = expected_gain(0.4, 0.3, "review", 1.0)
    density = value_density(0.4, 0.3, 0.8, 0.12, 20, 1.0, 20)
    assert why["expected_gain"] == gain
    assert why["density"] == density["density"]
    assert why["if_skipped"]["lost_gain"] == gain
    assert why["if_skipped"]["expected_gain"] == 0.0
    assert str(gain) in why["if_skipped"]["summary"]
    delayed_r = round(0.8 * (0.9 ** (1.0 / 7.0)), 4)
    assert why["if_delayed_1d"]["retention"] == delayed_r
    assert why["if_min_tier"]["minutes"] == 5
    assert why["if_min_tier"]["density"] > why["density"]
    assert why["version"] == "rules-v2.1"


def test_flashcards_use_phase_target_retention(db, db_user_goal):
    user, goal = db_user_goal
    point = KnowledgePoint(goal_id=goal.id, name="阶段目标保持率", weight=1.0)
    db.add(point)
    goal.exam_date = date.today() + timedelta(days=50)
    db.commit()

    deck = build_deck(db, user.id, goal.id)
    assert deck["phase"] == "foundation"
    assert deck["target_retention"] == 0.85
    card = deck["cards"][0]
    assert card["target_retention"] == 0.85
    assert card["phase_label"] == "基础期"
