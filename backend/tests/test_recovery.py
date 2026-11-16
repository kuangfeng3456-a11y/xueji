"""无邮件/短信通道下的自助找回：密保问题 + 一次性恢复码。"""


def _register(api, username="alice", password="secret123"):
    response = api("POST", "/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


ANSWERS = [
    {"question_key": "birth_city", "answer": "杭州"},
    {"question_key": "primary_school", "answer": "实验小学"},
]


def _setup_questions(api, token, password="secret123", answers=None):
    return api(
        "PUT",
        "/api/auth/security/questions",
        token=token,
        json={"password": password, "answers": answers or ANSWERS},
    )


def _verify_questions(api, answers=None, username="alice"):
    return api(
        "POST",
        "/api/auth/recovery/verify",
        json={"username": username, "method": "questions", "answers": answers or ANSWERS},
    )


def test_security_overview_starts_empty(api):
    token = _register(api)
    body = api("GET", "/api/auth/security", token=token).json()
    assert body["has_questions"] is False
    assert body["codes_unused"] == 0
    assert body["recovery_ready"] is False


def test_setting_questions_requires_password(api):
    token = _register(api)

    bad = _setup_questions(api, token, password="wrong-password")
    assert bad.status_code == 400
    assert "密码" in bad.json()["detail"]

    ok = _setup_questions(api, token)
    assert ok.status_code == 200
    body = ok.json()
    assert body["has_questions"] is True
    assert body["recovery_ready"] is True
    assert [item["key"] for item in body["questions"]] == ["birth_city", "primary_school"]
    assert all(item["text"] for item in body["questions"])


def test_setting_questions_rejects_duplicate_keys(api):
    token = _register(api)
    response = _setup_questions(
        api,
        token,
        answers=[
            {"question_key": "birth_city", "answer": "杭州"},
            {"question_key": "birth_city", "answer": "上海"},
        ],
    )
    assert response.status_code == 400
    assert "两个不同" in response.json()["detail"]


def test_options_expose_methods_and_question_texts(api):
    token = _register(api)
    _setup_questions(api, token)

    body = api("GET", "/api/auth/recovery/options", params={"username": "alice"}).json()
    assert "questions" in body["methods"]
    assert len(body["questions"]) == 2
    assert "出生" in "".join(item["text"] for item in body["questions"])


def test_options_for_unknown_user_return_no_methods(api):
    body = api("GET", "/api/auth/recovery/options", params={"username": "nobody"}).json()
    assert body["methods"] == []


def test_answers_ignore_case_and_spaces(api):
    token = _register(api)
    _setup_questions(
        api,
        token,
        answers=[
            {"question_key": "birth_city", "answer": "HangZhou"},
            {"question_key": "primary_school", "answer": " 实验小学 "},
        ],
    )

    response = _verify_questions(
        api,
        answers=[
            {"question_key": "birth_city", "answer": " hang zhou "},
            {"question_key": "primary_school", "answer": "实验小学"},
        ],
    )
    assert response.status_code == 200
    assert response.json()["reset_token"]


def test_verify_then_reset_password(api):
    token = _register(api)
    _setup_questions(api, token)
    ticket = _verify_questions(api).json()["reset_token"]

    reset = api(
        "POST", "/api/auth/recovery/reset", json={"reset_token": ticket, "new_password": "newpass789"}
    )
    assert reset.status_code == 204

    assert api("POST", "/api/auth/login", json={"username": "alice", "password": "secret123"}).status_code == 400
    assert api("POST", "/api/auth/login", json={"username": "alice", "password": "newpass789"}).status_code == 200
    # 重设密码后旧会话全部作废
    assert api("GET", "/api/auth/me", token=token).status_code == 401


def test_wrong_answers_are_rejected_and_generic(api):
    token = _register(api)
    _setup_questions(api, token)

    response = _verify_questions(
        api,
        answers=[
            {"question_key": "birth_city", "answer": "北京"},
            {"question_key": "primary_school", "answer": "实验小学"},
        ],
    )
    assert response.status_code == 400
    assert "验证信息不正确" in response.json()["detail"]


def test_unknown_user_response_is_identical_to_wrong_answer(api):
    response = _verify_questions(api, username="nobody")
    assert response.status_code == 400
    assert "验证信息不正确" in response.json()["detail"]


def test_too_many_failures_lock_recovery_temporarily(api):
    token = _register(api)
    _setup_questions(api, token)
    wrong = [
        {"question_key": "birth_city", "answer": "北京"},
        {"question_key": "primary_school", "answer": "实验小学"},
    ]

    for _ in range(5):
        assert _verify_questions(api, answers=wrong).status_code == 400

    blocked = _verify_questions(api)
    assert blocked.status_code == 429
    assert "次数过多" in blocked.json()["detail"]

    # 锁定期间即使答案正确也不放行
    options = api("GET", "/api/auth/recovery/options", params={"username": "alice"}).json()
    assert options["locked_until"]


def test_reset_token_is_single_use(api):
    token = _register(api)
    _setup_questions(api, token)
    ticket = _verify_questions(api).json()["reset_token"]

    first = api("POST", "/api/auth/recovery/reset", json={"reset_token": ticket, "new_password": "newpass789"})
    assert first.status_code == 204

    second = api("POST", "/api/auth/recovery/reset", json={"reset_token": ticket, "new_password": "another123"})
    assert second.status_code == 400
    assert "失效" in second.json()["detail"]


def test_reset_rejects_same_password(api):
    token = _register(api)
    _setup_questions(api, token)
    ticket = _verify_questions(api).json()["reset_token"]

    response = api(
        "POST", "/api/auth/recovery/reset", json={"reset_token": ticket, "new_password": "secret123"}
    )
    assert response.status_code == 400
    assert "不能与原密码相同" in response.json()["detail"]


def test_recovery_codes_are_shown_once_and_single_use(api):
    token = _register(api)

    issued = api("POST", "/api/auth/security/codes", token=token, json={"password": "secret123"})
    assert issued.status_code == 200
    codes = issued.json()["codes"]
    assert len(codes) == 8
    assert all(code.startswith("XJ-") for code in codes)

    # 明文不再出现在任何读取接口里
    overview = api("GET", "/api/auth/security", token=token).json()
    assert overview["codes_unused"] == 8
    assert "codes" not in overview

    verify = api(
        "POST",
        "/api/auth/recovery/verify",
        json={"username": "alice", "method": "code", "code": codes[0].lower()},
    )
    assert verify.status_code == 200
    assert verify.json()["method"] == "code"

    # 同一枚码不能再用第二次
    reused = api(
        "POST",
        "/api/auth/recovery/verify",
        json={"username": "alice", "method": "code", "code": codes[0]},
    )
    assert reused.status_code == 400


def test_regenerating_codes_invalidates_old_batch(api):
    token = _register(api)
    first = api("POST", "/api/auth/security/codes", token=token, json={"password": "secret123"}).json()["codes"]
    second = api("POST", "/api/auth/security/codes", token=token, json={"password": "secret123"}).json()["codes"]

    old = api(
        "POST", "/api/auth/recovery/verify", json={"username": "alice", "method": "code", "code": first[0]}
    )
    assert old.status_code == 400

    new = api(
        "POST", "/api/auth/recovery/verify", json={"username": "alice", "method": "code", "code": second[0]}
    )
    assert new.status_code == 200


def test_code_setup_requires_password(api):
    token = _register(api)
    response = api("POST", "/api/auth/security/codes", token=token, json={"password": "nope"})
    assert response.status_code == 400


def test_method_questions_without_setup_points_to_codes(api):
    _register(api)
    response = _verify_questions(api)
    assert response.status_code == 400
    assert "恢复码" in response.json()["detail"]


def test_delete_account_purges_security_records(api, db):
    from app.models import AuthSession, RecoveryCode, RecoveryProfile

    token = _register(api)
    _setup_questions(api, token)
    api("POST", "/api/auth/security/codes", token=token, json={"password": "secret123"})

    assert api("DELETE", "/api/auth/me", token=token).status_code == 204

    assert db.query(AuthSession).count() == 0
    assert db.query(RecoveryProfile).count() == 0
    assert db.query(RecoveryCode).count() == 0
