from datetime import date


def test_daily_review_empty_then_upsert_and_dashboard(api, auth, goal):
    token = auth["token"]
    goal_id = goal["id"]

    empty = api("GET", f"/api/goals/{goal_id}/daily-review", token=token)
    assert empty.status_code == 200
    assert empty.json() is None

    created = api(
        "PUT",
        f"/api/goals/{goal_id}/daily-review",
        token=token,
        json={
            "energy": 2,
            "hard_note": "阅读长难句",
            "extra_learned": "记了5个词根",
            "next_pace": "lighter",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["energy"] == 2
    assert body["hard_note"] == "阅读长难句"
    assert body["extra_learned"] == "记了5个词根"
    assert body["next_pace"] == "lighter"
    assert body["day"] == date.today().isoformat()
    assert body["suggestion"]
    review_id = body["id"]

    updated = api(
        "PUT",
        f"/api/goals/{goal_id}/daily-review",
        token=token,
        json={
            "energy": 4,
            "hard_note": "完形填空",
            "extra_learned": "",
            "next_pace": "same",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == review_id
    assert updated.json()["energy"] == 4
    assert updated.json()["hard_note"] == "完形填空"
    assert updated.json()["next_pace"] == "same"

    dash = api("GET", "/api/dashboard", token=token).json()
    assert dash["daily_review"]["id"] == review_id
    assert dash["daily_review"]["energy"] == 4
    assert dash["daily_review"]["hard_note"] == "完形填空"


def test_daily_review_rejects_invalid_energy_and_pace(api, auth, goal):
    token = auth["token"]
    goal_id = goal["id"]
    bad_energy = api(
        "PUT",
        f"/api/goals/{goal_id}/daily-review",
        token=token,
        json={"energy": 0, "next_pace": "same"},
    )
    assert bad_energy.status_code == 422
    bad_pace = api(
        "PUT",
        f"/api/goals/{goal_id}/daily-review",
        token=token,
        json={"energy": 3, "next_pace": "sprint"},
    )
    assert bad_pace.status_code == 422


def test_dashboard_without_goals_has_empty_daily_review(api, auth):
    body = api("GET", "/api/dashboard", token=auth["token"]).json()
    assert body["goal"] is None
    assert body["daily_review"] is None
