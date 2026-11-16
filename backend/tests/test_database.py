"""database.py 单元测试：RDS 探活、SQLite 自动降级与连接生命周期。

测试不创建任何真实 MySQL 连接：所有探活与引擎工厂均使用替身对象，
确保单元测试永不访问华为云 RDS。
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import database as database_module


class FakeConnection:
    def __init__(self, value="1"):
        self.value = value
        self.executed = []

    def execute(self, statement):
        self.executed.append(str(statement))
        return SimpleNamespace(scalar=lambda: self.value)


class FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection
        self.exited = False

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False


class FakeEngine:
    def __init__(self, probe_error=None):
        self.probe_error = probe_error
        self.disposed = False
        self.connection = FakeConnection()

    def connect(self):
        if self.probe_error:
            raise self.probe_error
        return FakeConnectionContext(self.connection)

    def dispose(self):
        self.disposed = True


# ---------------------------------------------------------------- 引擎创建


def test_create_engine_sqlite_disables_thread_check():
    factory = MagicMock(return_value=object())
    with patch.object(database_module, "create_engine", factory):
        result = database_module._create_engine("sqlite:///D:/tmp/test.db")

    assert result is factory.return_value
    factory.assert_called_once_with(
        "sqlite:///D:/tmp/test.db",
        connect_args={"check_same_thread": False, "timeout": 10},
    )


def test_create_engine_rds_uses_pool_and_ssl_options(monkeypatch):
    monkeypatch.setattr(database_module.settings, "RDS_SSL_CA", "/etc/rds-ca.pem")
    factory = MagicMock(return_value=object())
    with patch.object(database_module, "create_engine", factory):
        database_module._create_engine("mysql+pymysql://user:pwd@rds-host:3306/xueji")

    factory.assert_called_once()
    _, kwargs = factory.call_args
    assert kwargs["connect_args"] == {
        "connect_timeout": 3,
        "ssl": {"ca": "/etc/rds-ca.pem"},
    }
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20
    assert kwargs["pool_recycle"] == 1800
    assert kwargs["pool_timeout"] == 30


def test_create_engine_rds_without_ssl(monkeypatch):
    monkeypatch.setattr(database_module.settings, "RDS_SSL_CA", "")
    factory = MagicMock(return_value=object())
    with patch.object(database_module, "create_engine", factory):
        database_module._create_engine("mysql+pymysql://user:pwd@rds-host:3306/xueji")

    _, kwargs = factory.call_args
    assert kwargs["connect_args"] == {"connect_timeout": 3}


# ---------------------------------------------------------------- 探活


def test_probe_database_returns_empty_on_success():
    target = FakeEngine()

    assert database_module._probe_database(target) == ""
    assert target.connection.executed == ["SELECT 1"]


def test_probe_database_truncates_error_message():
    target = FakeEngine(probe_error=RuntimeError("x" * 500))

    error = database_module._probe_database(target)

    assert error == "x" * 200


# ---------------------------------------------------------------- 降级决策


def test_resolve_database_keeps_sqlite_without_probe():
    primary = MagicMock(name="primary_engine")
    factory = MagicMock(return_value=primary)
    probe = MagicMock()

    runtime = database_module.resolve_database(
        "sqlite:///D:/data/dev.db", engine_factory=factory, probe=probe
    )

    factory.assert_called_once_with("sqlite:///D:/data/dev.db")
    probe.assert_not_called()
    primary.dispose.assert_not_called()
    assert runtime.url == "sqlite:///D:/data/dev.db"
    assert runtime.backend == "sqlite"
    assert runtime.fallback is False
    assert runtime.error == ""
    assert runtime.engine is primary


def test_resolve_database_keeps_rds_when_probe_succeeds():
    primary = MagicMock(name="primary_engine")
    factory = MagicMock(return_value=primary)
    probe = MagicMock(return_value="")

    runtime = database_module.resolve_database(
        "mysql+pymysql://user:pwd@rds-host:3306/xueji",
        engine_factory=factory,
        probe=probe,
        local_sqlite=Path("D:/data/fallback.db"),
    )

    factory.assert_called_once_with("mysql+pymysql://user:pwd@rds-host:3306/xueji")
    probe.assert_called_once_with(primary)
    primary.dispose.assert_not_called()
    assert runtime.backend == "rds"
    assert runtime.fallback is False
    assert runtime.url.startswith("mysql+pymysql://")


def test_resolve_database_falls_back_to_sqlite_when_rds_unreachable():
    primary = MagicMock(name="primary_engine")
    fallback = MagicMock(name="fallback_engine")
    factory = MagicMock(side_effect=[primary, fallback])
    probe = MagicMock(return_value="(2003, \"Can't connect\")")

    runtime = database_module.resolve_database(
        "mysql+pymysql://user:pwd@rds-host:3306/xueji",
        engine_factory=factory,
        probe=probe,
        local_sqlite=Path("D:/data/fallback.db"),
    )

    assert factory.call_args_list[0].args == (
        "mysql+pymysql://user:pwd@rds-host:3306/xueji",
    )
    assert factory.call_args_list[1].args == ("sqlite:///D:/data/fallback.db",)
    primary.dispose.assert_called_once()
    fallback.dispose.assert_not_called()
    assert runtime.url == "sqlite:///D:/data/fallback.db"
    assert runtime.backend == "sqlite-fallback"
    assert runtime.fallback is True
    assert runtime.error == "(2003, \"Can't connect\")"
    assert runtime.engine is fallback


def test_resolve_database_creates_fallback_even_if_file_missing(tmp_path):
    """本地 SQLite 不存在时也应自动创建，而不是放弃降级。"""
    primary = MagicMock(name="primary_engine")
    fallback = MagicMock(name="fallback_engine")
    factory = MagicMock(side_effect=[primary, fallback])
    missing = tmp_path / "not-created-yet.db"
    assert not missing.exists()

    runtime = database_module.resolve_database(
        "mysql+pymysql://user:pwd@rds-host:3306/xueji",
        engine_factory=factory,
        probe=MagicMock(return_value="timeout"),
        local_sqlite=missing,
    )

    assert runtime.fallback is True
    assert runtime.url == f"sqlite:///{missing.as_posix()}"


# ---------------------------------------------------------------- 会话生命周期


def test_get_db_yields_session_and_closes_when_generator_closes():
    session = MagicMock(name="session")
    with patch.object(database_module, "SessionLocal", return_value=session):
        generator = database_module.get_db()
        assert next(generator) is session
        generator.close()

    session.close.assert_called_once()


def test_get_db_closes_session_when_consumer_raises():
    session = MagicMock(name="session")
    with patch.object(database_module, "SessionLocal", return_value=session):
        generator = database_module.get_db()
        next(generator)
        with pytest.raises(RuntimeError, match="boom"):
            generator.throw(RuntimeError("boom"))

    session.close.assert_called_once()