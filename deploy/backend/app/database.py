import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger("xueji.database")
LOCAL_SQLITE = Path(__file__).resolve().parent.parent / "xueji.db"
FALLBACK_URL_PREFIX = "sqlite:///"


def _create_engine(url: str):
    if url.startswith("sqlite"):
        # busy timeout：写锁等待上限，避免并发写入时长时间卡住
        return create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 10}
        )
    # connect_timeout 保持短值：RDS 不可达时启动探活能快速失败并回退本地 SQLite，
    # 避免拖慢冷启动（Windows 上 TCP SYN 重传叠加会放大默认超时）。
    connect_args = {"connect_timeout": 3}
    if settings.RDS_SSL_CA:
        connect_args["ssl"] = {"ca": settings.RDS_SSL_CA}
    return create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_timeout=30,
    )


def _probe_database(target: Engine) -> str:
    """探测数据库可用性，成功返回空串，失败返回截断后的错误信息。"""
    try:
        with target.connect() as connection:
            connection.execute(text("SELECT 1"))
        return ""
    except Exception as exc:  # pragma: no cover - 具体异常类型依赖驱动
        return str(exc)[:200]


@dataclass(frozen=True)
class DatabaseRuntime:
    """启动时确定的数据库运行状态，便于测试与健康检查复用。"""

    url: str
    backend: str
    fallback: bool
    error: str
    engine: Engine


def resolve_database(
    primary_url: str,
    *,
    engine_factory: Callable[[str], Engine] = _create_engine,
    probe: Callable[[Engine], str] = _probe_database,
    local_sqlite: Path = LOCAL_SQLITE,
) -> DatabaseRuntime:
    """解析数据库后端；RDS 不可达时自动降级为本地 SQLite。

    生产环境仍优先使用华为云 RDS MySQL。只有在探活失败时才切换到
    sqlite-fallback，保证云数据库故障时服务可继续提供只读/应急能力。
    """
    backend = "rds" if "mysql" in primary_url else "sqlite"
    active_engine = engine_factory(primary_url)

    if backend != "rds":
        return DatabaseRuntime(primary_url, backend, False, "", active_engine)

    error = probe(active_engine)
    if not error:
        return DatabaseRuntime(primary_url, backend, False, "", active_engine)

    active_engine.dispose()
    fallback_url = f"{FALLBACK_URL_PREFIX}{local_sqlite.as_posix()}"
    fallback_engine = engine_factory(fallback_url)
    return DatabaseRuntime(fallback_url, "sqlite-fallback", True, error, fallback_engine)


PRIMARY_DATABASE_URL = settings.DATABASE_URL
_runtime = resolve_database(PRIMARY_DATABASE_URL)
ACTIVE_DATABASE_URL = _runtime.url
ACTIVE_DATABASE_BACKEND = _runtime.backend
DATABASE_FALLBACK = _runtime.fallback
DATABASE_ERROR = _runtime.error

engine = _runtime.engine

if ACTIVE_DATABASE_BACKEND == "rds":
    logger.info("云数据库 RDS 连接正常")
elif DATABASE_FALLBACK:
    logger.warning("RDS 不可达，已自动回退本地 SQLite：%s", DATABASE_ERROR)
else:
    logger.info("使用本地 SQLite 数据库：%s", ACTIVE_DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()