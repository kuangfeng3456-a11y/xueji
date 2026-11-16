"""学习策略自动实验室（experiments）单元测试。"""

from datetime import date, datetime, timedelta

from app.models import KnowledgePoint, LearningExperiment, Mastery
from app.services.experiments import (
    _avg_mastery,
    build_ranking,
    experiment_dict,
    finish_experiment,
    list_experiments,
    start_experiment,
)


def _point(db, goal, name):
    point = KnowledgePoint(goal_id=goal.id, name=name, weight=1.0)
    db.add(point)
    db.flush()
    return point


def _mastery(db, user, point, value):
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=value))
    db.flush()


def _finished(db, user, goal, strategy, pre, post, created_at=None):
    experiment = LearningExperiment(
        user_id=user.id,
        goal_id=goal.id,
        strategy=strategy,
        status="finished",
        days=3,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        pre_mastery=pre,
        post_mastery=post,
        created_at=created_at or datetime(2026, 1, 1),
    )
    db.add(experiment)
    db.flush()
    return experiment


# --------------------------------------------------------------------------
# _avg_mastery
# --------------------------------------------------------------------------


def test_avg_mastery_returns_zero_without_rows(db, db_user_goal):
    user, goal = db_user_goal

    assert _avg_mastery(db, user.id, goal.id) == 0.0


def test_avg_mastery_averages_points_in_goal(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "听力")
    second = _point(db, goal, "阅读")
    _mastery(db, user, first, 0.2)
    _mastery(db, user, second, 0.6)
    db.commit()

    assert _avg_mastery(db, user.id, goal.id) == 0.4


# --------------------------------------------------------------------------
# experiment_dict / start / finish
# --------------------------------------------------------------------------


def test_experiment_dict_exposes_gain_and_scores(db, db_user_goal):
    user, goal = db_user_goal
    experiment = _finished(db, user, goal, "practice", 0.2, 0.6)
    experiment.immediate_score = 82
    experiment.delayed_score = 70
    experiment.note = "三日实验"
    db.commit()

    payload = experiment_dict(experiment)

    assert payload["id"] == experiment.id
    assert payload["strategy"] == "practice"
    assert payload["gain"] == 0.4
    assert payload["immediate_score"] == 82
    assert payload["delayed_score"] == 70
    assert payload["note"] == "三日实验"


def test_experiment_dict_flags_overdue_running_experiment(db, db_user_goal):
    """到期未收尾的实验要能被前端标出来，否则「进行中」会一直挂着。"""
    user, goal = db_user_goal
    experiment = start_experiment(db, user, goal, "read", 3, today=date.today() - timedelta(days=5))

    payload = experiment_dict(experiment)

    assert payload["status"] == "running"
    assert payload["expired"] is True
    assert payload["overdue_days"] == 3
    assert payload["days_left"] == -3


def test_experiment_dict_running_within_window_is_not_expired(db, db_user_goal):
    user, goal = db_user_goal
    experiment = start_experiment(db, user, goal, "practice", 3, today=date.today())

    payload = experiment_dict(experiment)

    assert payload["expired"] is False
    assert payload["overdue_days"] == 0
    assert payload["days_left"] == 2


def test_finished_experiment_is_never_marked_expired(db, db_user_goal):
    user, goal = db_user_goal
    experiment = _finished(db, user, goal, "read", 0.2, 0.5)
    db.commit()

    payload = experiment_dict(experiment)

    assert payload["status"] == "finished"
    assert payload["expired"] is False
    assert payload["overdue_days"] == 0
    assert payload["days_left"] == 0


def test_start_experiment_records_dates_and_baseline(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "听力")
    _mastery(db, user, point, 0.3)
    db.commit()

    experiment = start_experiment(db, user, goal, "read", 3, today=date(2026, 3, 1))
    assert experiment.status == "running"
    assert experiment.days == 3
    assert experiment.start_date == date(2026, 3, 1)
    assert experiment.end_date == date(2026, 3, 3)
    assert experiment.pre_mastery == 0.3
    assert experiment.post_mastery == 0.3
    assert experiment.id is not None


def test_finish_experiment_updates_mastery_scores_and_status(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "听力")
    _mastery(db, user, point, 0.3)
    db.commit()
    experiment = start_experiment(db, user, goal, "flashcard", 3, today=date(2026, 3, 1))
    point_mastery = db.query(Mastery).one()
    point_mastery.value = 0.7
    db.commit()

    updated = finish_experiment(
        db,
        user,
        experiment,
        85,
        72,
        "闪卡效果更好",
        today=date(2026, 3, 5),
    )

    assert updated.status == "finished"
    assert updated.post_mastery == 0.7
    assert updated.immediate_score == 85
    assert updated.delayed_score == 72
    assert updated.note == "闪卡效果更好"
    assert updated.end_date == date(2026, 3, 5)
    assert experiment_dict(updated)["gain"] == 0.4


# --------------------------------------------------------------------------
# build_ranking / list_experiments
# --------------------------------------------------------------------------


def test_build_ranking_groups_finished_experiments_by_strategy(db, db_user_goal):
    user, goal = db_user_goal
    _finished(db, user, goal, "read", 0.1, 0.3)
    _finished(db, user, goal, "read", 0.2, 0.4)
    _finished(db, user, goal, "practice", 0.4, 0.45)
    db.add(
        LearningExperiment(
            user_id=user.id,
            goal_id=goal.id,
            strategy="flashcard",
            status="running",
            days=3,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
            pre_mastery=0.1,
            post_mastery=0.9,
        )
    )
    db.commit()

    ranking = build_ranking(db, user.id, goal.id)

    assert [item["strategy"] for item in ranking] == ["read", "practice"]
    assert ranking[0]["label"] == "精读理解"
    assert ranking[0]["avg_gain"] == 0.2
    assert ranking[0]["experiments"] == 2
    assert ranking[1]["avg_gain"] == 0.05
    assert ranking[1]["experiments"] == 1


def test_build_ranking_is_empty_without_finished_experiments(db, db_user_goal):
    user, goal = db_user_goal

    assert build_ranking(db, user.id, goal.id) == []


def test_list_experiments_orders_by_created_at_and_exposes_strategies(db, db_user_goal):
    user, goal = db_user_goal
    older = _finished(db, user, goal, "read", 0.1, 0.2, created_at=datetime(2026, 1, 1))
    newer = _finished(db, user, goal, "practice", 0.2, 0.5, created_at=datetime(2026, 2, 1))
    db.commit()

    payload = list_experiments(db, user.id, goal.id)

    assert [item["id"] for item in payload["items"]] == [newer.id, older.id]
    assert [item["key"] for item in payload["strategies"]] == [
        "read",
        "practice",
        "flashcard",
        "ai_tutor",
    ]
    assert payload["strategies"][0] == {"key": "read", "label": "精读理解"}
    assert len(payload["ranking"]) == 2


def test_list_experiments_without_rows_returns_empty_payload(db, db_user_goal):
    user, goal = db_user_goal

    payload = list_experiments(db, user.id, goal.id)

    assert payload["items"] == []
    assert payload["ranking"] == []
    assert len(payload["strategies"]) == 4