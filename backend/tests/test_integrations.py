"""integrations 模块单元测试。

覆盖：接入清单（含数据库降级状态）、各依赖探活分支、汇总调度与 API 端点。
DeepSeek 与数据库探活全部替换为 Mock，测试期间不会发出真实模型请求，
也不会连接真实 RDS。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import integrations as integrations_module
from app.services.integrations import (
    _base_host,
    _test_cache,
    _test_database,
    _test_deepseek,
    _test_storage,
    describe_integrations,
)
from app.services.integrations import test_integrations as probe_integrations


def run(coro):
    return asyncio.run(coro)


DESCRIBED = {
    "items": [
        {
            "key": "deepseek",
            "name": "DeepSeek 模型接口",
            "type": "model",
            "configured": True,
            "detail": "deepseek-chat · api.deepseek.com",
        },
        {
            "key": "database",
            "name": "业务数据库",
            "type": "cloud",
            "configured": False,
            "status": "degraded",
            "detail": "已回退 SQLite",
        },
        {
            "key": "cache",
            "name": "分布式缓存",
            "type": "cloud",
            "configured": True,
            "detail": "DCS Redis",
        },
        {
            "key": "storage",
            "name": "文件存储",
            "type": "network",
            "configured": True,
            "detail": "/data/uploads",
        },
        {
            "key": "speech",
            "name": "语音识别 / 合成",
            "type": "browser",
            "configured": True,
            "detail": "浏览器 Web Speech API",
        },
        {
            "key": "camera",
            "name": "摄像头",
            "type": "browser",
            "configured": True,
            "detail": "getUserMedia",
        },
        {
            "key": "ocr",
            "name": "错题 OCR",
            "type": "network",
            "configured": False,
            "status": "not_configured",
            "detail": "华为云 OCR 未配置",
        },
        {
            "key": "sis",
            "name": "语音 SIS",
            "type": "network",
            "configured": False,
            "status": "not_configured",
            "detail": "华为云 SIS 未配置",
        },
        {
            "key": "external",
            "name": "外部知识库",
            "type": "network",
            "configured": False,
            "detail": "当前网络仅放行模型接口",
        },
    ],
    "status": "degraded",
    "degraded_count": 1,
    "configured_count": 5,
    "total": 9,
}


def _settings(**overrides):
    values = {
        "LLM_BASE_URL": "",
        "LLM_MODEL": "pangu",
        "RDS_HOST": "",
        "RDS_PORT": "3306",
        "RDS_DATABASE": "xueji",
        "CLOUD_REGION": "cn-north-4",
        "REDIS_HOST": "",
        "REDIS_PORT": "6379",
        "UPLOAD_DIR": "/data/uploads",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _describe(settings, backend, error="", llm_available=False, cache_backend="memory"):
    llm_mock = MagicMock()
    llm_mock.available = llm_available
    cache_mock = MagicMock()
    cache_mock.backend = cache_backend
    kb_mock = MagicMock()
    kb_mock.describe.return_value = {
        "configured": False,
        "status": "unknown",
        "detail": "未探测外部知识源",
        "sources": [],
    }

    with patch.object(integrations_module, "settings", settings), patch.object(
        integrations_module, "llm", llm_mock
    ), patch.object(integrations_module, "cache", cache_mock), patch.object(
        integrations_module, "knowledge_base", kb_mock
    ), patch.object(
        integrations_module, "ACTIVE_DATABASE_BACKEND", backend
    ), patch.object(
        integrations_module, "DATABASE_ERROR", error
    ):
        return describe_integrations()


# ---------------------------------------------------------------- 地址解析


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://api.deepseek.com/v1", "api.deepseek.com"),
        ("api.deepseek.com/v1", "api.deepseek.com/v1"),
        ("", ""),
    ],
)
def test_base_host_extracts_host(url, expected):
    settings_mock = SimpleNamespace(LLM_BASE_URL=url)
    with patch.object(integrations_module, "settings", settings_mock):
        assert _base_host() == expected


# ---------------------------------------------------------------- 接入清单


def test_describe_integrations_reports_local_defaults():
    result = _describe(_settings(), "sqlite")

    items = {item["key"]: item for item in result["items"]}
    assert [item["key"] for item in result["items"]] == [
        "deepseek",
        "question_bank",
        "video_sources",
        "database",
        "cache",
        "storage",
        "speech",
        "camera",
        "ocr",
        "sis",
        "external",
    ]
    assert items["video_sources"]["configured"] is True
    assert items["deepseek"]["configured"] is False
    assert items["deepseek"]["detail"] == "pangu · 未配置地址"
    assert items["question_bank"]["configured"] is False
    assert items["database"]["configured"] is False
    assert items["database"]["status"] == "not_configured"
    assert items["database"]["detail"] == "SQLite（开发模式，未接入 RDS）"
    assert items["cache"]["configured"] is False
    assert items["cache"]["detail"] == "内存缓存（未接入 DCS Redis；DCS 公网暂不可达）"
    assert items["storage"]["detail"] == "/data/uploads"
    assert items["speech"]["status"] == "degraded"
    assert items["ocr"]["status"] == "not_configured"
    assert items["sis"]["status"] == "not_configured"
    assert items["external"]["configured"] is False
    # 语音未接 SIS 时如实标注为降级，因此整体状态是 degraded 而不是 ok
    assert result["status"] == "degraded"
    assert result["degraded_count"] == 1
    assert result["configured_count"] == 3
    assert result["total"] == 11


def test_describe_integrations_reports_remote_backends():
    settings_mock = _settings(
        LLM_BASE_URL="https://api.deepseek.com/v1",
        LLM_MODEL="deepseek-chat",
        RDS_HOST="rds-abc",
        RDS_PORT="3306",
        RDS_DATABASE="xueji",
        CLOUD_REGION="cn-north-4",
        REDIS_HOST="dcs-abc",
        REDIS_PORT="6379",
    )

    result = _describe(
        settings_mock, "rds", llm_available=True, cache_backend="redis"
    )

    items = {item["key"]: item for item in result["items"]}
    assert items["deepseek"]["configured"] is True
    assert items["deepseek"]["detail"] == "deepseek-chat · api.deepseek.com"
    assert items["database"]["configured"] is True
    assert items["database"]["status"] == "ok"
    assert items["database"]["detail"] == "华为云 RDS MySQL · rds-abc:3306/xueji · cn-north-4"
    assert items["cache"]["configured"] is True
    assert items["cache"]["detail"] == "华为云 DCS Redis · dcs-abc:6379 · cn-north-4"
    # 语音/OCR 仍未配置，因此整体仍如实标注为 degraded
    assert result["status"] == "degraded"
    assert result["degraded_count"] == 1
    assert result["configured_count"] == 6
    assert result["total"] == 11


def test_describe_integrations_marks_sqlite_fallback_as_degraded():
    error = "x" * 200

    result = _describe(_settings(), "sqlite-fallback", error=error)

    database = next(item for item in result["items"] if item["key"] == "database")
    assert database["configured"] is False
    assert database["status"] == "degraded"
    assert database["detail"] == f"RDS 不可达，已自动回退本地 SQLite · {'x' * 80}"
    assert result["status"] == "degraded"
    # 数据库回退 + 语音未接 SIS，两处降级
    assert result["degraded_count"] == 2
    assert result["configured_count"] == 3


# ---------------------------------------------------------------- DeepSeek 探活


def test_test_deepseek_not_configured():
    llm_mock = MagicMock()
    llm_mock.available = False
    with patch.object(integrations_module, "llm", llm_mock):
        result = run(_test_deepseek())

    assert result == {
        "status": "not_configured",
        "latency_ms": None,
        "detail": "未配置 LLM_API_KEY",
    }
    llm_mock.chat.assert_not_called()


def test_test_deepseek_ok_reports_latency_and_reply():
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [10.0, 10.25]
    llm_mock = MagicMock()
    llm_mock.available = True
    llm_mock.chat = AsyncMock(return_value="  OK  ")

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "llm", llm_mock
    ):
        result = run(_test_deepseek())

    assert result == {"status": "ok", "latency_ms": 250, "detail": "模型回复：OK"}
    llm_mock.chat.assert_awaited_once_with(
        "只回复 OK", "ping", temperature=0, max_tokens=5
    )
    assert time_mock.perf_counter.call_count == 2


def test_test_deepseek_error_when_reply_blank():
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [1.0, 1.1]
    llm_mock = MagicMock()
    llm_mock.available = True
    llm_mock.chat = AsyncMock(return_value="")

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "llm", llm_mock
    ):
        result = run(_test_deepseek())

    assert result == {
        "status": "error",
        "latency_ms": 100,
        "detail": "调用失败，已自动回退规则引擎",
    }


# ---------------------------------------------------------------- 数据库探活


def _database_probe(backend, value="8.0.32", error=None, perf=None):
    engine_mock = MagicMock()
    if error is not None:
        engine_mock.connect.side_effect = error
    else:
        connection = engine_mock.connect.return_value.__enter__.return_value
        connection.execute.return_value.scalar.return_value = value
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = perf or [1.0, 1.5]

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "engine", engine_mock
    ), patch.object(integrations_module, "ACTIVE_DATABASE_BACKEND", backend):
        result = _test_database()
    return result, engine_mock


def test_test_database_rds_queries_version_and_reports_ok():
    result, engine_mock = _database_probe("rds", value="8.0.32")

    assert result == {"status": "ok", "latency_ms": 500, "detail": "连接正常 · 8.0.32"}
    connection = engine_mock.connect.return_value.__enter__.return_value
    assert str(connection.execute.call_args.args[0]) == "SELECT VERSION()"
    engine_mock.connect.return_value.__exit__.assert_called_once()


def test_test_database_sqlite_queries_sqlite_version():
    result, engine_mock = _database_probe("sqlite", value="3.45.0")

    assert result == {"status": "ok", "latency_ms": 500, "detail": "连接正常 · 3.45.0"}
    connection = engine_mock.connect.return_value.__enter__.return_value
    assert str(connection.execute.call_args.args[0]) == "SELECT sqlite_version()"


def test_test_database_sqlite_fallback_returns_degraded():
    result, _ = _database_probe("sqlite-fallback", value="3.45.0")

    assert result == {
        "status": "degraded",
        "latency_ms": 500,
        "detail": "RDS 不可达，已回退 SQLite 3.45.0",
    }


def test_test_database_error_truncates_message():
    result, _ = _database_probe("rds", error=RuntimeError("x" * 200))

    assert result["status"] == "error"
    assert result["latency_ms"] is None
    assert result["detail"] == "x" * 120


# ---------------------------------------------------------------- 缓存探活


def test_test_cache_ok_memory_roundtrip():
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [2.0, 2.5]
    cache_mock = MagicMock()
    cache_mock.backend = "memory"
    cache_mock.get_json.return_value = {"ok": True}
    cache_mock.info.return_value = {"backend": "memory"}

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "cache", cache_mock
    ):
        result = _test_cache()

    assert result == {
        "status": "degraded",
        "latency_ms": 500,
        "detail": "进程内存缓存读写正常，未接入 DCS Redis",
    }
    key = cache_mock.set_json.call_args.args[0]
    assert key.startswith("integration:ping:")
    cache_mock.set_json.assert_called_once_with(key, {"ok": True}, ttl=10)
    cache_mock.get_json.assert_called_once_with(key)
    cache_mock.delete.assert_called_once_with(key)


def test_test_cache_ok_redis_detail():
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [3.0, 3.1]
    cache_mock = MagicMock()
    cache_mock.backend = "redis"
    cache_mock.get_json.return_value = {"ok": True}
    cache_mock.info.return_value = {
        "version": "7.2.3",
        "used_memory_human": "1.2M",
    }

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "cache", cache_mock
    ):
        result = _test_cache()

    assert result["status"] == "ok"
    assert result["detail"] == "Redis 7.2.3 读写正常 · 内存 1.2M"
    assert result["latency_ms"] == 100
    cache_mock.info.assert_called_once_with()


def test_test_cache_reports_error_when_value_missing():
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [4.0, 4.2]
    cache_mock = MagicMock()
    cache_mock.backend = "memory"
    cache_mock.get_json.return_value = {}
    cache_mock.info.return_value = {"backend": "memory"}

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "cache", cache_mock
    ):
        result = _test_cache()

    assert result["status"] == "error"
    assert result["latency_ms"] == 200
    cache_mock.delete.assert_called_once()


def test_test_cache_error_when_exception():
    time_mock = MagicMock()
    time_mock.perf_counter.side_effect = [5.0, 5.1]
    cache_mock = MagicMock()
    cache_mock.backend = "memory"
    cache_mock.set_json.side_effect = RuntimeError("y" * 200)

    with patch.object(integrations_module, "time", time_mock), patch.object(
        integrations_module, "cache", cache_mock
    ):
        result = _test_cache()

    assert result["status"] == "error"
    assert result["latency_ms"] is None
    assert result["detail"] == "y" * 120


# ---------------------------------------------------------------- 存储探活


def test_test_storage_ok_writes_and_removes_probe(tmp_path, monkeypatch):
    settings_mock = SimpleNamespace(UPLOAD_DIR=str(tmp_path))
    monkeypatch.setattr(integrations_module, "settings", settings_mock)

    result = _test_storage()

    assert result["status"] == "ok"
    assert result["detail"] == "读写正常"
    health_dir = tmp_path / "_health"
    assert health_dir.is_dir()
    assert list(health_dir.iterdir()) == []


def test_test_storage_error_when_target_blocked(tmp_path, monkeypatch):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    settings_mock = SimpleNamespace(UPLOAD_DIR=str(blocker))
    monkeypatch.setattr(integrations_module, "settings", settings_mock)

    result = _test_storage()

    assert result["status"] == "error"
    assert result["latency_ms"] is None
    assert result["detail"]
    assert len(result["detail"]) <= 120


# ---------------------------------------------------------------- 汇总探活


def test_test_integrations_dispatches_every_provider_and_keeps_degraded():
    async_mock = AsyncMock(
        return_value={"status": "ok", "latency_ms": 12, "detail": "ping 正常"}
    )
    sync_ok = {"status": "ok", "latency_ms": 3, "detail": "正常"}
    degraded = {"status": "degraded", "latency_ms": 7, "detail": "回退 SQLite"}

    with patch.object(
        integrations_module, "describe_integrations", return_value=DESCRIBED
    ), patch.object(
        integrations_module, "_test_deepseek", new=async_mock
    ), patch.object(
        integrations_module, "_test_database", return_value=degraded
    ) as db_mock, patch.object(
        integrations_module, "_test_cache", return_value=sync_ok
    ) as cache_mock, patch.object(
        integrations_module, "_test_storage", return_value=sync_ok
    ) as storage_mock, patch.object(
        integrations_module.knowledge_base, "probe", new=AsyncMock(return_value=[])
    ):
        results = run(probe_integrations())

    assert len(results) == 9
    by_key = {item["key"]: item for item in results}
    assert by_key["deepseek"] == {
        **DESCRIBED["items"][0],
        "status": "ok",
        "latency_ms": 12,
        "detail": "ping 正常",
    }
    assert by_key["database"] == {
        **DESCRIBED["items"][1],
        "status": "degraded",
        "latency_ms": 7,
        "detail": "回退 SQLite",
    }
    assert by_key["cache"]["detail"] == "正常"
    assert by_key["speech"]["status"] == "client"
    assert by_key["speech"]["detail"] == "由浏览器提供，需在页面中授权"
    assert by_key["camera"]["status"] == "client"
    assert by_key["ocr"]["status"] == "unavailable"
    assert by_key["sis"]["status"] == "unavailable"
    assert by_key["external"]["status"] == "unavailable"
    assert by_key["external"]["configured"] is False

    async_mock.assert_awaited_once_with()
    db_mock.assert_called_once_with()
    cache_mock.assert_called_once_with()
    storage_mock.assert_called_once_with()


# ---------------------------------------------------------------- API 端点


def test_integrations_endpoint_returns_descriptions(api, auth):
    payload = {
        "items": [{"key": "deepseek", "configured": False}],
        "status": "degraded",
        "degraded_count": 1,
        "configured_count": 0,
        "total": 1,
    }
    with patch("app.api.integrations.describe_integrations", return_value=payload):
        response = api("GET", "/api/integrations", token=auth["token"])

    assert response.status_code == 200
    assert response.json() == payload


def test_integrations_test_endpoint_counts_health_and_degraded(api, auth):
    items = [
        {"key": "deepseek", "configured": True, "status": "ok"},
        {"key": "speech", "configured": True, "status": "client"},
        {"key": "external", "configured": False, "status": "unavailable"},
        {"key": "database", "configured": True, "status": "degraded"},
    ]
    with patch(
        "app.api.integrations.test_integrations", new=AsyncMock(return_value=items)
    ):
        response = api("POST", "/api/integrations/test", token=auth["token"])

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == items
    assert body["status"] == "degraded"
    assert body["configured_count"] == 3
    assert body["healthy_count"] == 2
    assert body["degraded_count"] == 1
    assert body["total"] == 4
    assert body["tested_at"] is None


@pytest.mark.parametrize(
    "method,path",
    [("GET", "/api/integrations"), ("POST", "/api/integrations/test")],
)
def test_integrations_endpoints_require_auth(api, method, path):
    response = api(method, path)
    assert response.status_code == 401