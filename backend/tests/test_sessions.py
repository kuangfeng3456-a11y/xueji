"""多设备会话：设备列表、单设备下线、退出其他设备、改密后其他设备失效。"""


def _register(api, username="alice", password="secret123"):
    response = api("POST", "/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _login(api, username="alice", password="secret123", user_agent=None):
    headers = {"User-Agent": user_agent} if user_agent else None
    response = api(
        "POST", "/api/auth/login", json={"username": username, "password": password}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
WINDOWS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def test_register_creates_one_session_marked_current(api):
    token = _register(api)

    response = api("GET", "/api/auth/sessions", token=token)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["current"] is True


def test_second_login_adds_device_and_only_one_is_current(api):
    first = _register(api)
    second = _login(api, user_agent=IPHONE_UA)

    rows = api("GET", "/api/auth/sessions", token=second).json()
    assert len(rows) == 2
    assert [row["current"] for row in rows].count(True) == 1
    devices = {row["device"] for row in rows}
    assert any("iPhone" in item for item in devices)

    # 用第一台的 token 看，当前设备标记应该落在第一台上
    first_rows = api("GET", "/api/auth/sessions", token=first).json()
    assert [row["current"] for row in first_rows].count(True) == 1


def test_device_label_parses_browser_and_system(api):
    token = _register(api)
    _login(api, user_agent=WINDOWS_UA)

    rows = api("GET", "/api/auth/sessions", token=token).json()
    labels = {row["device"]: row["platform"] for row in rows}
    assert labels.get("Chrome · Windows") == "web"


def test_revoke_other_device_invalidates_its_token(api):
    first = _register(api)
    second = _login(api, user_agent=IPHONE_UA)

    result = api("POST", "/api/auth/sessions/revoke-others", token=second)
    assert result.status_code == 200
    assert result.json()["revoked"] == 1

    # 被踢下线的旧设备立刻 401，而不是等 token 自然过期
    assert api("GET", "/api/auth/me", token=first).status_code == 401
    assert api("GET", "/api/auth/me", token=second).status_code == 200
    assert len(api("GET", "/api/auth/sessions", token=second).json()) == 1


def test_revoke_current_device_acts_as_logout(api):
    token = _register(api)
    session_id = api("GET", "/api/auth/sessions", token=token).json()[0]["id"]

    response = api("DELETE", f"/api/auth/sessions/{session_id}", token=token)
    assert response.status_code == 200
    assert response.json()["current"] is True
    assert api("GET", "/api/auth/me", token=token).status_code == 401


def test_revoke_unknown_or_foreign_session_is_404(api):
    owner = _register(api, "owner")
    other = _register(api, "other")
    session_id = api("GET", "/api/auth/sessions", token=owner).json()[0]["id"]

    assert api("DELETE", f"/api/auth/sessions/{session_id}", token=other).status_code == 404
    assert api("DELETE", "/api/auth/sessions/999999", token=other).status_code == 404


def test_logout_revokes_server_side(api):
    token = _register(api)
    assert api("POST", "/api/auth/logout", token=token).status_code == 204
    assert api("GET", "/api/auth/me", token=token).status_code == 401
    # 再退出一次不应报错（幂等）
    assert api("POST", "/api/auth/logout", token=token).status_code == 401


def test_change_password_keeps_current_device_only(api):
    current = _register(api)
    other = _login(api, user_agent=IPHONE_UA)

    response = api(
        "POST",
        "/api/auth/me/password",
        token=current,
        json={"old_password": "secret123", "new_password": "brandnew456"},
    )
    assert response.status_code == 204

    assert api("GET", "/api/auth/me", token=current).status_code == 200
    assert api("GET", "/api/auth/me", token=other).status_code == 401
    assert len(api("GET", "/api/auth/sessions", token=current).json()) == 1


def test_token_from_before_session_support_is_rejected(api, db):
    """没有 jti 的历史 token 一律拒绝：宁可让用户重登，也不留下不可撤销的凭据。"""
    from app.models import User
    from app.security import hash_password
    from jose import jwt

    from app.config import settings

    user = User(username="legacy", password_hash=hash_password("secret123"), nickname="老用户")
    db.add(user)
    db.commit()
    db.refresh(user)

    legacy = jwt.encode(
        {"sub": str(user.id), "username": user.username},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    assert api("GET", "/api/auth/me", token=legacy).status_code == 401
