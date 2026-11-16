"""学科 Skill 包市场（skill_packages service + api）单元测试。"""

import json

import pytest
from sqlalchemy import select

import app.services.skill_packages as skill_packages_module
from app.models import KnowledgePoint, Mastery, SkillPackage
from app.services.skill_packages import (
    PACKAGES,
    apply_package,
    ensure_packages,
    package_views,
)


def _package(slug):
    return next(item for item in PACKAGES if item["slug"] == slug)


def _row(db, slug):
    return db.scalar(select(SkillPackage).where(SkillPackage.slug == slug))


# --------------------------------------------------------------------------
# ensure_packages
# --------------------------------------------------------------------------


def test_ensure_packages_creates_all_builtin_packages(db):
    ensure_packages(db)
    db.commit()

    rows = db.scalars(select(SkillPackage)).all()
    assert len(rows) == len(PACKAGES)
    assert len(PACKAGES) >= 10
    assert {row.slug for row in rows} == {item["slug"] for item in PACKAGES}

    cet4 = _row(db, "cet4")
    assert cet4.name == "大学英语四级包"
    assert cet4.subject == "英语"
    assert cet4.tags == "四六级,大学英语,词汇"
    assert cet4.official is True
    config = json.loads(cet4.config)
    assert config["points"] == _package("cet4")["points"]


def test_ensure_packages_is_idempotent_and_refreshes_fields(db):
    ensure_packages(db)
    db.commit()
    row = _row(db, "cet4")
    row.name = "旧名字"
    row.tags = ""
    db.commit()

    ensure_packages(db)
    db.commit()

    assert db.scalars(select(SkillPackage)).all().__len__() == len(PACKAGES)
    refreshed = _row(db, "cet4")
    assert refreshed.name == "大学英语四级包"
    assert refreshed.tags == "四六级,大学英语,词汇"


# --------------------------------------------------------------------------
# package_views
# --------------------------------------------------------------------------


def test_package_views_without_goal_reports_zero_applied(db):
    views = package_views(db, None)

    assert len(views) == len(PACKAGES)
    cet4 = next(item for item in views if item["slug"] == "cet4")
    expected = _package("cet4")
    assert cet4["name"] == expected["name"]
    assert cet4["subject"] == expected["subject"]
    assert cet4["description"] == expected["description"]
    assert cet4["tags"] == expected["tags"]
    assert cet4["official"] is True
    assert cet4["point_count"] == len(expected["points"])
    assert cet4["applied_count"] == 0
    assert cet4["applied"] is False
    assert cet4["points"] == [item["name"] for item in expected["points"]]


def test_package_views_counts_partially_applied_points(db, db_user_goal):
    user, goal = db_user_goal
    db.add(KnowledgePoint(goal_id=goal.id, name="听力", weight=1.0))
    db.commit()

    cet4 = next(item for item in package_views(db, goal) if item["slug"] == "cet4")

    assert cet4["applied_count"] == 1
    assert cet4["point_count"] == len(_package("cet4")["points"])
    assert cet4["applied"] is False


def test_package_views_marks_fully_applied_package(db, db_user_goal):
    user, goal = db_user_goal
    for item in _package("cet4")["points"]:
        db.add(KnowledgePoint(goal_id=goal.id, name=item["name"], weight=1.0))
    db.commit()

    cet4 = next(item for item in package_views(db, goal) if item["slug"] == "cet4")

    assert cet4["applied_count"] == cet4["point_count"]
    assert cet4["applied"] is True


def test_package_views_matches_names_case_insensitively(db, db_user_goal):
    user, goal = db_user_goal
    db.add(KnowledgePoint(goal_id=goal.id, name="听力", weight=1.0))
    db.commit()

    cet4 = next(item for item in package_views(db, goal) if item["slug"] == "cet4")

    assert cet4["applied_count"] == 1


def test_package_views_tolerates_broken_config(db, monkeypatch):
    ensure_packages(db)
    db.commit()
    row = _row(db, "kaoyan-math")
    row.config = "not-json"
    db.commit()
    monkeypatch.setattr(skill_packages_module, "ensure_packages", lambda session: None)

    view = next(
        item for item in package_views(db, None) if item["slug"] == "kaoyan-math"
    )

    assert view["point_count"] == 0
    assert view["points"] == []
    assert view["applied"] is False
    assert view["applied_count"] == 0


def test_package_views_filters_empty_tags(db, monkeypatch):
    ensure_packages(db)
    db.commit()
    row = _row(db, "cet4")
    row.tags = "四六级,,大学英语,"
    db.commit()
    monkeypatch.setattr(skill_packages_module, "ensure_packages", lambda session: None)

    view = next(item for item in package_views(db, None) if item["slug"] == "cet4")

    assert view["tags"] == ["四六级", "大学英语"]


# --------------------------------------------------------------------------
# apply_package
# --------------------------------------------------------------------------


def test_apply_package_rejects_unknown_slug(db, db_user_goal):
    user, goal = db_user_goal

    with pytest.raises(ValueError) as excinfo:
        apply_package(db, user.id, goal, "not-exist")

    assert str(excinfo.value) == "Skill 包不存在"


def test_apply_package_creates_points_and_mastery(db, db_user_goal):
    user, goal = db_user_goal
    expected = _package("cet4")

    result = apply_package(db, user.id, goal, "cet4")

    assert result == {
        "package": "大学英语四级包",
        "created": len(expected["points"]),
        "total": len(expected["points"]),
    }
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    assert len(points) == len(expected["points"])
    assert {point.name for point in points} == {
        item["name"] for item in expected["points"]
    }
    mastery_rows = db.scalars(
        select(Mastery).where(Mastery.user_id == user.id)
    ).all()
    assert len(mastery_rows) == len(expected["points"])
    assert all(row.value == 0.0 for row in mastery_rows)


def test_apply_package_does_not_duplicate_existing_points(db, db_user_goal):
    user, goal = db_user_goal
    apply_package(db, user.id, goal, "cet4")

    second = apply_package(db, user.id, goal, "cet4")

    assert second["created"] == 0
    assert second["total"] == len(_package("cet4")["points"])


def test_apply_package_tolerates_broken_config(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    ensure_packages(db)
    db.commit()
    row = _row(db, "computer-level2")
    row.config = "broken"
    db.commit()
    monkeypatch.setattr(skill_packages_module, "ensure_packages", lambda session: None)

    result = apply_package(db, user.id, goal, "computer-level2")

    assert result == {"package": "计算机二级 Python 包", "created": 0, "total": 0}


# --------------------------------------------------------------------------
# /api/skill-packages 接口
# --------------------------------------------------------------------------


def test_list_packages_api(api, auth):
    response = api("GET", "/api/skill-packages", token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == len(PACKAGES)
    cet4 = body[0]
    assert cet4["slug"] == "cet4"
    assert cet4["official"] is True
    assert cet4["applied"] is False
    assert cet4["applied_count"] == 0
    assert cet4["point_count"] == len(_package("cet4")["points"])


def test_list_packages_with_goal_reports_applied(api, auth, goal, imported_points):
    response = api(
        "GET", "/api/skill-packages", token=auth["token"], params={"goal_id": goal["id"]}
    )

    assert response.status_code == 200, response.text
    cet4 = next(item for item in response.json() if item["slug"] == "cet4")
    assert cet4["applied_count"] > 0
    assert cet4["applied"] is False


def test_list_packages_rejects_unknown_goal(api, auth):
    response = api(
        "GET", "/api/skill-packages", token=auth["token"], params={"goal_id": 999999}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"


def test_apply_package_api(api, auth, goal):
    response = api(
        "POST",
        "/api/skill-packages/cet4/apply",
        token=auth["token"],
        json={"goal_id": goal["id"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["package"] == "大学英语四级包"
    assert body["created"] == len(_package("cet4")["points"])
    assert body["total"] == len(_package("cet4")["points"])

    listing = api(
        "GET", "/api/skill-packages", token=auth["token"], params={"goal_id": goal["id"]}
    ).json()
    assert next(item for item in listing if item["slug"] == "cet4")["applied"] is True


def test_apply_package_api_rejects_unknown_slug(api, auth, goal):
    response = api(
        "POST",
        "/api/skill-packages/ghost/apply",
        token=auth["token"],
        json={"goal_id": goal["id"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Skill 包不存在"


def test_apply_package_api_rejects_foreign_goal(api, auth):
    response = api(
        "POST",
        "/api/skill-packages/cet4/apply",
        token=auth["token"],
        json={"goal_id": 999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "目标不存在"