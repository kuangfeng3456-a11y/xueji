"""应用入口（main.py）测试：建表、生命周期、访问日志、异常映射与健康检查。"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import main as main_module
from app.config import settings as app_settings
from app.database import engine
from app.main import (
    UPLOAD_DIR,
    access_log,
    app,
    database_exception_handler,
    ensure_schema,
    health,
    lifespan,
    unhandled_exception_handler,
)


LEGACY_MISTAKES = """
CREATE TABLE mistakes (
    id INTEGER NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    goal_id INTEGER NOT NULL,
    kp_id INTEGER,
    question TEXT NOT NULL,
    user_answer TEXT,
    correct_answer TEXT,
    category VARCHAR(32),
    category_label VARCHAR(32),
    suggestion TEXT,
    source VARCHAR(32),
    created_at DATETIME
)
"""

LEGACY_GOALS = """
CREATE TABLE goals (
    id INTEGER NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    exam_name VARCHAR(255) NOT NULL,
    exam_date DATE NOT NULL,
    daily_minutes INTEGER,
    force_mode BOOLEAN DEFAULT 0
)
"""

LEGACY_TASKS = """
CREATE TABLE tasks (
    id INTEGER NOT NULL PRIMARY KEY,
    goal_id INTEGER NOT NULL,
    kp_id INTEGER,
    title VARCHAR(255) NOT NULL,
    planned_date DATE,
    duration_minutes INTEGER,
    status VARCHAR(16),
    skip_reason VARCHAR(255)
)
"""


def _columns(table):
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _request(path="/api/health", method="GET", request_id=None):
    headers = {}
    state = SimpleNamespace()
    if request_id:
        headers["X-Request-ID"] = request_id
        # 与 access_log 中间件保持一致，便于直接调用异常处理器时读取 request_id
        state.request_id = request_id
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers=headers,
        state=state,
    )


# ---------------------------------------------------------------- 建表


def test_ensure_schema_adds_image_url_to_legacy_table(db):
    db.execute(text("DROP TABLE mistakes"))
    db.execute(text(LEGACY_MISTAKES))
    db.commit()
    assert "image_url" not in _columns("mistakes")

    ensure_schema()

    assert "image_url" in _columns("mistakes")


def test_ensure_schema_is_idempotent_when_column_exists(db):
    ensure_schema()
    assert "image_url" in _columns("mistakes")

    ensure_schema()

    assert "image_url" in _columns("mistakes")


def test_ensure_schema_creates_missing_tables(db):
    db.execute(text("DROP TABLE IF EXISTS mistakes"))
    db.commit()

    ensure_schema()

    assert "mistakes" in inspect(engine).get_table_names()
    assert "image_url" in _columns("mistakes")


def test_ensure_schema_skips_existing_and_adds_missing_columns(db):
    db.execute(text("DROP TABLE goals"))
    db.execute(text("DROP TABLE tasks"))
    db.execute(text(LEGACY_GOALS))
    db.execute(text(LEGACY_TASKS))
    db.commit()

    ensure_schema()

    goal_columns = _columns("goals")
    assert {"force_mode", "min_daily_minutes", "camera_required"} <= goal_columns
    assert "skip_reason" in _columns("tasks")
    assert "feedback" in _columns("tasks")


# ---------------------------------------------------------------- 生命周期


def test_lifespan_initializes_schema_and_upload_dir():
    async def run():
        async with lifespan(app):
            pass

    asyncio.run(run())

    assert UPLOAD_DIR.exists()
    assert "users" in inspect(engine).get_table_names()


def test_lifespan_logs_warning_when_database_fallback(monkeypatch):
    logger_mock = MagicMock()
    monkeypatch.setattr(main_module, "ensure_schema", MagicMock())
    monkeypatch.setattr(main_module, "logger", logger_mock)
    monkeypatch.setattr(main_module, "DATABASE_FALLBACK", True)
    monkeypatch.setattr(main_module, "DATABASE_ERROR", "rds down")
    monkeypatch.setattr(main_module, "ACTIVE_DATABASE_BACKEND", "sqlite-fallback")
    monkeypatch.setattr(main_module, "cache", SimpleNamespace(backend="memory"))
    monkeypatch.setattr(main_module, "llm", SimpleNamespace(available=False))

    async def run():
        async with lifespan(app):
            pass

    asyncio.run(run())

    logger_mock.info.assert_called_once()
    logger_mock.warning.assert_called_once_with("云数据库降级运行：%s", "rds down")


# ---------------------------------------------------------------- 访问日志


def test_access_log_writes_latency_and_request_id():
    request = _request("/api/orders", method="GET", request_id="trace-abc")
    response = SimpleNamespace(status_code=201, headers={})
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [10.0, 10.125]

    async def call_next(_):
        return response

    with patch.object(main_module, "time", time_mock), patch.object(
        main_module, "logger"
    ) as logger_mock:
        result = asyncio.run(access_log(request, call_next))

    assert result is response
    assert response.headers["X-Request-ID"] == "trace-abc"
    assert response.headers["X-Trace-Id"] == "trace-abc"
    assert request.state.request_id == "trace-abc"
    logger_mock.info.assert_called_once_with(
        "%s %s -> %s %sms trace_id=%s",
        "GET",
        "/api/orders",
        201,
        125.0,
        "trace-abc",
    )


def test_access_log_generates_request_id_when_header_missing():
    request = _request("/api/health")
    response = SimpleNamespace(status_code=200, headers={})

    async def call_next(_):
        return response

    with patch.object(main_module, "logger"):
        asyncio.run(access_log(request, call_next))

    generated = response.headers["X-Request-ID"]
    assert generated == request.state.request_id
    assert len(generated) == 12
    assert all(char in "0123456789abcdef" for char in generated)


def test_access_log_logs_and_reraises_exception():
    request = _request("/api/boom", method="POST", request_id="trace-x")

    async def call_next(_):
        raise RuntimeError("boom")

    with patch.object(main_module, "logger") as logger_mock:
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(access_log(request, call_next))

    logger_mock.exception.assert_called_once_with(
        "请求异常 %s %s request_id=%s", "POST", "/api/boom", "trace-x"
    )


# ---------------------------------------------------------------- 异常处理器


def test_database_exception_handler_returns_503_with_request_id():
    request = _request("/api/plan", request_id="rid-9")

    response = asyncio.run(database_exception_handler(request, SQLAlchemyError("down")))

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "detail": "数据库暂不可用，请检查云数据库状态或稍后重试",
        "request_id": "rid-9",
    }


def test_unhandled_exception_handler_returns_500_with_request_id():
    request = _request("/api/plan", request_id="rid-10")

    response = asyncio.run(unhandled_exception_handler(request, RuntimeError("boom")))

    assert response.status_code == 500
    assert json.loads(response.body) == {
        "detail": "服务内部错误，已记录日志",
        "request_id": "rid-10",
    }


def test_exception_handler_uses_unknown_request_id_when_state_missing():
    request = _request("/api/plan")
    assert not hasattr(request.state, "request_id")

    response = asyncio.run(unhandled_exception_handler(request, RuntimeError("boom")))

    assert json.loads(response.body)["request_id"] == "unknown"


def test_sqlalchemy_error_is_mapped_to_503_by_api(api, auth):
    with patch(
        "app.api.integrations.describe_integrations",
        side_effect=SQLAlchemyError("db down"),
    ):
        response = api("GET", "/api/integrations", token=auth["token"])

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "数据库暂不可用，请检查云数据库状态或稍后重试"
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_unhandled_error_is_mapped_to_500_by_api(api, auth):
    with patch(
        "app.api.integrations.describe_integrations",
        side_effect=RuntimeError("unexpected"),
    ):
        response = api("GET", "/api/integrations", token=auth["token"])

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "服务内部错误，已记录日志"
    assert body["request_id"]


# ---------------------------------------------------------------- 健康检查


def test_health_reports_ok_backends(monkeypatch):
    monkeypatch.setattr(main_module, "ACTIVE_DATABASE_BACKEND", "rds")
    monkeypatch.setattr(main_module, "DATABASE_FALLBACK", False)
    monkeypatch.setattr(main_module, "DATABASE_ERROR", "")
    monkeypatch.setattr(main_module, "cache", SimpleNamespace(backend="redis"))
    monkeypatch.setattr(main_module, "llm", SimpleNamespace(available=True))

    result = health()

    assert result == {
        "status": "ok",
        "app": app_settings.APP_NAME,
        "version": app_settings.VERSION,
        "database": "rds",
        "database_fallback": False,
        "database_error": "",
        "cache": "redis",
        "llm": True,
    }


def test_health_reports_degraded_with_truncated_error(monkeypatch):
    monkeypatch.setattr(main_module, "ACTIVE_DATABASE_BACKEND", "sqlite-fallback")
    monkeypatch.setattr(main_module, "DATABASE_FALLBACK", True)
    monkeypatch.setattr(main_module, "DATABASE_ERROR", "e" * 200)
    monkeypatch.setattr(main_module, "cache", SimpleNamespace(backend="memory"))
    monkeypatch.setattr(main_module, "llm", SimpleNamespace(available=False))

    result = health()

    assert result["status"] == "degraded"
    assert result["database"] == "sqlite-fallback"
    assert result["database_fallback"] is True
    assert result["database_error"] == "e" * 120
    assert result["cache"] == "memory"
    assert result["llm"] is False


def test_health_endpoint_exposes_degraded_status(api, monkeypatch):
    monkeypatch.setattr(main_module, "ACTIVE_DATABASE_BACKEND", "sqlite-fallback")
    monkeypatch.setattr(main_module, "DATABASE_FALLBACK", True)
    monkeypatch.setattr(main_module, "DATABASE_ERROR", "rds timeout")
    monkeypatch.setattr(main_module, "cache", SimpleNamespace(backend="memory"))
    monkeypatch.setattr(main_module, "llm", SimpleNamespace(available=False))

    response = api("GET", "/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "sqlite-fallback"
    assert body["database_fallback"] is True
    assert body["database_error"] == "rds timeout"