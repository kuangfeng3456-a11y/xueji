"""账号与安全：资料修改、改密码、演示口令不外泄。"""


def _register(api, username="alice", password="secret123"):
    response = api(
        "POST",
        "/api/auth/register",
        json={"username": username, "password": password, "nickname": "小林", "school": "计算机学院"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_update_profile_changes_nickname_and_school(api):
    token = _register(api)

    response = api(
        "PATCH", "/api/auth/me", token=token, json={"nickname": "林同学", "school": "信息工程学院"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["nickname"] == "林同学"
    assert body["school"] == "信息工程学院"
    assert body["username"] == "alice"

    # 改动落到库：再读一次仍是新值
    again = api("GET", "/api/auth/me", token=token)
    assert again.json()["nickname"] == "林同学"


def test_update_profile_rejects_blank_nickname(api):
    token = _register(api, "bob")

    response = api("PATCH", "/api/auth/me", token=token, json={"nickname": "   "})
    assert response.status_code == 400
    assert "昵称" in response.json()["detail"]


def test_change_password_requires_old_password(api):
    token = _register(api, "carol", "secret123")

    wrong = api(
        "POST",
        "/api/auth/me/password",
        token=token,
        json={"old_password": "not-my-password", "new_password": "newsecret1"},
    )
    assert wrong.status_code == 400
    assert "原密码" in wrong.json()["detail"]

    # 失败后旧密码仍可登录
    still = api("POST", "/api/auth/login", json={"username": "carol", "password": "secret123"})
    assert still.status_code == 200


def test_change_password_then_login_with_new_one(api):
    token = _register(api, "dave", "secret123")

    ok = api(
        "POST",
        "/api/auth/me/password",
        token=token,
        json={"old_password": "secret123", "new_password": "brandnew456"},
    )
    assert ok.status_code == 204

    old_login = api("POST", "/api/auth/login", json={"username": "dave", "password": "secret123"})
    assert old_login.status_code == 400

    new_login = api("POST", "/api/auth/login", json={"username": "dave", "password": "brandnew456"})
    assert new_login.status_code == 200


def test_change_password_rejects_same_password(api):
    token = _register(api, "erin", "secret123")

    response = api(
        "POST",
        "/api/auth/me/password",
        token=token,
        json={"old_password": "secret123", "new_password": "secret123"},
    )
    assert response.status_code == 400
    assert "不能与原密码相同" in response.json()["detail"]


def test_meta_hides_demo_hint_by_default(api):
    """商用部署默认不在 /api/meta 里暴露演示账号。"""
    body = api("GET", "/api/meta").json()
    assert body["demo_hint"] == ""
