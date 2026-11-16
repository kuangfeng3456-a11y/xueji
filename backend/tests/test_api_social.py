"""班级看板与学习搭子（social service + api）单元测试。"""

from datetime import date, timedelta

from app.api import social as social_api
from app.models import (
    Buddy,
    ClassMember,
    Goal,
    KnowledgePoint,
    Mastery,
    SchoolClass,
    Task,
    User,
)
from app.services import social as social_service


TODAY = date(2026, 6, 10)


def _make_user(db, username, nickname="同学", school=None):
    user = User(username=username, password_hash="x", nickname=nickname, school=school)
    db.add(user)
    db.flush()
    return user


def _make_goal(db, user, name="CET-4", days=10):
    goal = Goal(
        user_id=user.id,
        exam_name=name,
        exam_date=TODAY + timedelta(days=days),
        daily_minutes=90,
    )
    db.add(goal)
    db.flush()
    return goal


def _add_mastery(db, user, goal, name, value):
    point = KnowledgePoint(goal_id=goal.id, name=name, weight=1.0)
    db.add(point)
    db.flush()
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=value))
    db.flush()
    return point


def _add_task(db, user, goal, day, status, title="任务"):
    db.add(
        Task(
            user_id=user.id,
            goal_id=goal.id,
            day=day,
            title=title,
            status=status,
            duration_min=20,
        )
    )


# --------------------------------------------------------------------------
# member_profile
# --------------------------------------------------------------------------


def test_member_profile_without_goal_returns_defaults(db):
    user = _make_user(db, "nogoal", "无目标")
    db.commit()

    profile = social_service.member_profile(db, user, today=TODAY)

    assert profile == {
        "user_id": user.id,
        "username": "nogoal",
        "nickname": "无目标",
        "school": None,
        "goal_name": None,
        "days_left": None,
        "streak": 0,
        "completion_rate": 0.0,
        "avg_mastery": 0.0,
        "weakest": None,
        "tasks_7d": 0,
        "done_7d": 0,
    }


def test_member_profile_aggregates_mastery_and_tasks(db):
    user = _make_user(db, "alice", "小艾", school="电子科大")
    goal = _make_goal(db, user)
    _add_mastery(db, user, goal, "听力", 0.3)
    _add_mastery(db, user, goal, "阅读", 0.6)
    _add_mastery(db, user, goal, "写作", 0.9)
    _add_task(db, user, goal, TODAY, "done", "今日完成")
    _add_task(db, user, goal, TODAY - timedelta(days=1), "done", "昨日完成")
    _add_task(db, user, goal, TODAY - timedelta(days=2), "pending", "前日待办")
    _add_task(db, user, goal, TODAY - timedelta(days=3), "skipped", "跳过任务")
    db.commit()

    profile = social_service.member_profile(db, user, today=TODAY)

    assert profile["goal_name"] == "CET-4"
    assert profile["days_left"] == 10
    assert profile["school"] == "电子科大"
    assert profile["avg_mastery"] == 0.6
    assert profile["weakest"] == "听力"
    assert profile["completion_rate"] == 0.6667
    assert profile["tasks_7d"] == 3
    assert profile["done_7d"] == 2
    assert profile["streak"] == 2


def test_member_profile_uses_latest_goal(db):
    from datetime import datetime

    user = _make_user(db, "bob", "小波")
    older = Goal(
        user_id=user.id,
        exam_name="旧目标",
        exam_date=TODAY + timedelta(days=3),
        daily_minutes=90,
        created_at=datetime(2026, 1, 1, 8, 0, 0),
    )
    newer = Goal(
        user_id=user.id,
        exam_name="新目标",
        exam_date=TODAY + timedelta(days=20),
        daily_minutes=90,
        created_at=datetime(2026, 2, 1, 8, 0, 0),
    )
    db.add_all([older, newer])
    db.commit()

    profile = social_service.member_profile(db, user, today=TODAY)

    assert profile["goal_name"] == "新目标"
    assert profile["days_left"] == 20


def test_member_profile_ignores_tasks_outside_week(db):
    user = _make_user(db, "carol", "小卡")
    goal = _make_goal(db, user)
    _add_task(db, user, goal, TODAY - timedelta(days=20), "done")
    db.commit()

    profile = social_service.member_profile(db, user, today=TODAY)

    assert profile["tasks_7d"] == 0
    assert profile["done_7d"] == 0
    assert profile["completion_rate"] == 0.0


# --------------------------------------------------------------------------
# class_members / build_class_dashboard
# --------------------------------------------------------------------------


def test_class_members_returns_empty_for_empty_class(db):
    owner = _make_user(db, "owner", "班长")
    school_class = SchoolClass(name="空班", description="", owner_id=owner.id, invite_code="EMPTY1")
    db.add(school_class)
    db.commit()

    assert social_service.class_members(db, school_class.id) == []


def test_class_members_returns_joined_users(db):
    first = _make_user(db, "u1", "甲")
    second = _make_user(db, "u2", "乙")
    school_class = SchoolClass(name="一班", description="", owner_id=first.id, invite_code="CLASS1")
    db.add(school_class)
    db.flush()
    db.add_all(
        [
            ClassMember(class_id=school_class.id, user_id=first.id, role="owner"),
            ClassMember(class_id=school_class.id, user_id=second.id, role="student"),
        ]
    )
    db.commit()

    members = social_service.class_members(db, school_class.id)

    assert {member.id for member in members} == {first.id, second.id}


def test_build_class_dashboard_empty(db):
    owner = _make_user(db, "owner", "班长")
    school_class = SchoolClass(name="空班", description="说明", owner_id=owner.id, invite_code="EMPTY2")
    db.add(school_class)
    db.commit()

    dashboard = social_service.build_class_dashboard(db, school_class, today=TODAY)

    assert dashboard["class_info"] == {
        "id": school_class.id,
        "name": "空班",
        "description": "说明",
        "invite_code": "EMPTY2",
        "owner_id": owner.id,
    }
    assert dashboard["member_count"] == 0
    assert dashboard["active_members"] == 0
    assert dashboard["avg_mastery"] == 0.0
    assert dashboard["avg_completion"] == 0.0
    assert dashboard["weak_points"] == []
    assert dashboard["members"] == []


def test_build_class_dashboard_aggregates_members(db):
    owner = _make_user(db, "owner", "班长")
    active = _make_user(db, "active", "活跃")
    quiet = _make_user(db, "quiet", "安静")
    nobody = _make_user(db, "nobody", "无目标")

    owner_goal = _make_goal(db, owner, name="CET-4")
    active_goal = _make_goal(db, active, name="考研数学")
    quiet_goal = _make_goal(db, quiet, name="HCIA")
    _add_mastery(db, owner, owner_goal, "总分", 0.5)
    _add_mastery(db, active, active_goal, "听力", 0.2)
    _add_mastery(db, active, active_goal, "阅读", 0.4)
    _add_mastery(db, quiet, quiet_goal, "听力", 0.6)
    _add_mastery(db, quiet, quiet_goal, "阅读", 0.8)
    _add_task(db, active, active_goal, TODAY, "done", "今日完成")
    _add_task(db, active, active_goal, TODAY, "pending", "今日待办")

    school_class = SchoolClass(name="高三一班", description="", owner_id=owner.id, invite_code="CLASS2")
    db.add(school_class)
    db.flush()
    for user in (owner, active, quiet, nobody):
        db.add(ClassMember(class_id=school_class.id, user_id=user.id, role="student"))
    db.commit()

    dashboard = social_service.build_class_dashboard(db, school_class, today=TODAY)

    assert dashboard["member_count"] == 4
    assert dashboard["active_members"] == 1
    assert dashboard["avg_mastery"] == 0.5
    assert dashboard["avg_completion"] == 0.5

    assert [item["name"] for item in dashboard["weak_points"]] == ["听力", "总分", "阅读"]
    hearing = dashboard["weak_points"][0]
    assert hearing["value"] == 0.4
    assert hearing["sample_count"] == 2
    assert dashboard["weak_points"][1]["value"] == 0.5
    assert dashboard["weak_points"][1]["sample_count"] == 1

    assert dashboard["members"][0]["user_id"] == active.id
    assert dashboard["members"][0]["streak"] == 1
    assert dashboard["members"][-1]["user_id"] == nobody.id
    assert dashboard["members"][-1]["goal_name"] is None


def test_build_class_dashboard_caps_weak_points_at_six(db):
    owner = _make_user(db, "owner", "班长")
    goal = _make_goal(db, owner)
    for index in range(8):
        _add_mastery(db, owner, goal, "知识点%d" % index, 0.1 * (index + 1))
    school_class = SchoolClass(name="大班", description="", owner_id=owner.id, invite_code="CLASS3")
    db.add(school_class)
    db.flush()
    db.add(ClassMember(class_id=school_class.id, user_id=owner.id, role="owner"))
    db.commit()

    dashboard = social_service.build_class_dashboard(db, school_class, today=TODAY)

    assert len(dashboard["weak_points"]) == 6
    assert dashboard["weak_points"][0]["name"] == "知识点0"
    assert dashboard["weak_points"][-1]["name"] == "知识点5"


# --------------------------------------------------------------------------
# buddy_profiles
# --------------------------------------------------------------------------


def test_buddy_profiles_without_buddies_only_returns_self(db):
    user = _make_user(db, "solo", "独行")
    db.commit()

    profiles = social_service.buddy_profiles(db, user, today=TODAY)

    assert len(profiles) == 1
    assert profiles[0]["user_id"] == user.id
    assert profiles[0]["is_me"] is True


def test_buddy_profiles_sorts_by_streak_and_marks_self(db):
    me = _make_user(db, "me", "我")
    friend = _make_user(db, "friend", "搭子")
    my_goal = _make_goal(db, me, name="CET-4")
    friend_goal = _make_goal(db, friend, name="考研数学")
    _add_task(db, friend, friend_goal, TODAY, "done")
    _add_task(db, friend, friend_goal, TODAY - timedelta(days=1), "done")
    db.add_all([Buddy(user_id=me.id, buddy_id=friend.id), Buddy(user_id=friend.id, buddy_id=me.id)])
    db.commit()

    profiles = social_service.buddy_profiles(db, me, today=TODAY)

    assert [profile["user_id"] for profile in profiles] == [friend.id, me.id]
    assert profiles[0]["streak"] == 2
    assert profiles[0]["completion_rate"] == 1.0
    assert profiles[0]["is_me"] is False
    assert profiles[1]["is_me"] is True
    assert my_goal.id is not None


# --------------------------------------------------------------------------
# /api/classes 与 /api/buddies 接口
# --------------------------------------------------------------------------


def _register(api, username, nickname="同学"):
    response = api(
        "POST",
        "/api/auth/register",
        json={"username": username, "password": "secret123", "nickname": nickname},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_class(api, token, name="高三一班", description="备考"):
    response = api(
        "POST",
        "/api/classes",
        token=token,
        json={"name": name, "description": description},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_class_brief_handles_missing_owner(db, db_user_goal):
    user, _ = db_user_goal
    school_class = SchoolClass(
        name="孤儿班", description="", owner_id=999999, invite_code="ORPHAN"
    )
    db.add(school_class)
    db.flush()
    db.add(ClassMember(class_id=school_class.id, user_id=user.id, role="student"))
    db.commit()

    brief = social_api._class_brief(db, school_class, user)

    assert brief["owner_name"] == ""
    assert brief["role"] == "student"
    assert brief["is_owner"] is False
    assert brief["member_count"] == 1
    assert brief["created_at"] == school_class.created_at.isoformat()


def test_create_and_list_classes(api, auth):
    created = _create_class(api, auth["token"])

    assert created["name"] == "高三一班"
    assert created["description"] == "备考"
    assert created["role"] == "owner"
    assert created["is_owner"] is True
    assert created["owner_name"] == "测试同学"
    assert created["member_count"] == 1
    assert len(created["invite_code"]) == 6
    assert created["invite_code"].isalnum()

    listing = api("GET", "/api/classes", token=auth["token"])
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created["id"]]


def test_list_classes_without_membership_is_empty(api, auth):
    response = api("GET", "/api/classes", token=auth["token"])

    assert response.status_code == 200
    assert response.json() == []


def test_join_class_by_invite_code(api, auth):
    created = _create_class(api, auth["token"])
    second = _register(api, "joiner", "小周")

    joined = api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": created["invite_code"].lower()},
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["role"] == "student"
    assert joined.json()["is_owner"] is False
    assert joined.json()["member_count"] == 2

    again = api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": created["invite_code"]},
    )
    assert again.status_code == 200
    assert again.json()["member_count"] == 2


def test_join_class_rejects_invalid_code(api, auth):
    second = _register(api, "joiner", "小周")

    response = api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": "ZZZZZZ"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "邀请码无效，请向老师或班长确认"


def test_leave_class_rejects_owner(api, auth):
    created = _create_class(api, auth["token"])

    response = api("POST", "/api/classes/%d/leave" % created["id"], token=auth["token"])

    assert response.status_code == 400
    assert response.json()["detail"] == "创建者不能退出班级，可删除班级"


def test_leave_class_rejects_non_member(api, auth):
    created = _create_class(api, auth["token"])
    outsider = _register(api, "outsider", "路人")

    response = api(
        "POST", "/api/classes/%d/leave" % created["id"], token=outsider["access_token"]
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "你不在该班级中"


def test_leave_class_removes_membership(api, auth):
    created = _create_class(api, auth["token"])
    second = _register(api, "joiner", "小周")
    api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": created["invite_code"]},
    )

    left = api(
        "POST", "/api/classes/%d/leave" % created["id"], token=second["access_token"]
    )

    assert left.status_code == 204
    assert left.text == ""
    assert api("GET", "/api/classes", token=second["access_token"]).json() == []


def test_leave_class_missing_class(api, auth):
    response = api("POST", "/api/classes/999999/leave", token=auth["token"])

    assert response.status_code == 404
    assert response.json()["detail"] == "班级不存在"


def test_delete_class_requires_owner(api, auth):
    created = _create_class(api, auth["token"])
    second = _register(api, "joiner", "小周")
    api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": created["invite_code"]},
    )

    forbidden = api(
        "DELETE", "/api/classes/%d" % created["id"], token=second["access_token"]
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "只有创建者可以删除班级"

    deleted = api("DELETE", "/api/classes/%d" % created["id"], token=auth["token"])
    assert deleted.status_code == 204
    assert api("GET", "/api/classes", token=auth["token"]).json() == []


def test_delete_class_missing_class(api, auth):
    response = api("DELETE", "/api/classes/999999", token=auth["token"])

    assert response.status_code == 404
    assert response.json()["detail"] == "班级不存在"


def test_class_dashboard_requires_membership(api, auth):
    created = _create_class(api, auth["token"])
    outsider = _register(api, "outsider", "路人")

    response = api(
        "GET",
        "/api/classes/%d/dashboard" % created["id"],
        token=outsider["access_token"],
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "请先加入班级"


def test_class_dashboard_missing_class(api, auth):
    response = api("GET", "/api/classes/999999/dashboard", token=auth["token"])

    assert response.status_code == 404
    assert response.json()["detail"] == "班级不存在"


def test_class_dashboard_returns_member_profiles(api, auth, goal):
    created = _create_class(api, auth["token"])

    response = api(
        "GET", "/api/classes/%d/dashboard" % created["id"], token=auth["token"]
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["member_count"] == 1
    assert body["class_info"]["name"] == "高三一班"
    assert body["members"][0]["user_id"] == auth["user"]["id"]
    assert body["members"][0]["goal_name"] == goal["exam_name"]
    assert body["weak_points"] == []


def test_remove_member_requires_owner(api, auth):
    created = _create_class(api, auth["token"])
    second = _register(api, "joiner", "小周")
    api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": created["invite_code"]},
    )

    response = api(
        "DELETE",
        "/api/classes/%d/members/%d" % (created["id"], auth["user"]["id"]),
        token=second["access_token"],
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "只有创建者可以移除成员"


def test_remove_member_rejects_self(api, auth):
    created = _create_class(api, auth["token"])

    response = api(
        "DELETE",
        "/api/classes/%d/members/%d" % (created["id"], auth["user"]["id"]),
        token=auth["token"],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "不能移除自己"


def test_remove_member_missing_member(api, auth):
    created = _create_class(api, auth["token"])

    response = api(
        "DELETE", "/api/classes/%d/members/999999" % created["id"], token=auth["token"]
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "成员不存在"


def test_remove_member_success(api, auth):
    created = _create_class(api, auth["token"])
    second = _register(api, "joiner", "小周")
    api(
        "POST",
        "/api/classes/join",
        token=second["access_token"],
        json={"invite_code": created["invite_code"]},
    )

    response = api(
        "DELETE",
        "/api/classes/%d/members/%d" % (created["id"], second["user"]["id"]),
        token=auth["token"],
    )

    assert response.status_code == 204
    dashboard = api(
        "GET", "/api/classes/%d/dashboard" % created["id"], token=auth["token"]
    ).json()
    assert dashboard["member_count"] == 1


def test_search_users_by_username_and_nickname(api, auth):
    _register(api, "zhangsan", "张三")
    _register(api, "lisi", "李四")

    assert api("GET", "/api/users/search?q=", token=auth["token"]).json() == []

    by_username = api("GET", "/api/users/search?q=zhang", token=auth["token"]).json()
    assert len(by_username) == 1
    assert by_username[0]["username"] == "zhangsan"
    assert by_username[0]["nickname"] == "张三"
    assert "id" in by_username[0] and "school" in by_username[0]

    by_nickname = api("GET", "/api/users/search?q=李", token=auth["token"]).json()
    assert [item["username"] for item in by_nickname] == ["lisi"]

    assert api("GET", "/api/users/search?q=tester", token=auth["token"]).json() == []


def test_search_users_limits_to_ten(api, auth):
    for index in range(12):
        _register(api, "member%02d" % index, "同学%d" % index)

    result = api("GET", "/api/users/search?q=member", token=auth["token"]).json()

    assert len(result) == 10


def test_add_buddy_rejects_unknown_user(api, auth):
    response = api(
        "POST", "/api/buddies", token=auth["token"], json={"username": "ghost"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "没有找到该用户名"


def test_add_buddy_rejects_self(api, auth):
    response = api(
        "POST", "/api/buddies", token=auth["token"], json={"username": "tester"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "不能添加自己为学习搭子"


def test_buddy_flow(api, auth):
    friend = _register(api, "friend01", "搭子")

    added = api(
        "POST", "/api/buddies", token=auth["token"], json={"username": "friend01"}
    )
    assert added.status_code == 201, added.text
    assert added.json()["user_id"] == friend["user"]["id"]
    assert added.json()["is_me"] is False

    repeated = api(
        "POST", "/api/buddies", token=auth["token"], json={"username": "friend01"}
    )
    assert repeated.status_code == 201

    listing = api("GET", "/api/buddies", token=auth["token"]).json()
    assert len(listing) == 2
    mine = [item for item in listing if item["is_me"]]
    assert len(mine) == 1
    assert mine[0]["username"] == "tester"

    removed = api(
        "DELETE", "/api/buddies/%d" % friend["user"]["id"], token=auth["token"]
    )
    assert removed.status_code == 204
    assert len(api("GET", "/api/buddies", token=auth["token"]).json()) == 1


def test_remove_buddy_is_idempotent(api, auth):
    response = api("DELETE", "/api/buddies/999999", token=auth["token"])

    assert response.status_code == 204


def test_generate_invite_code_retries_then_fails(api, auth, db, monkeypatch):
    user = db.get(User, auth["user"]["id"])
    db.add(SchoolClass(name="占位班", description="", owner_id=user.id, invite_code="AAAAAA"))
    db.commit()
    monkeypatch.setattr(social_api.random, "choice", lambda alphabet: "A")

    response = api(
        "POST", "/api/classes", token=auth["token"], json={"name": "新班级"}
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "邀请码生成失败，请重试"