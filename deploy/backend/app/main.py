import asyncio
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .api import (
    advanced,
    ai_lab,
    auth,
    admin,
    cloud_services,
    commitment,
    vocab,
    teaching,
    exam_prep,
    media_proxy,
    coach,
    cockpit,
    dashboard,
    entertainment,
    eval_center,
    family,
    evidence,
    experiments,
    focus,
    goals,
    insights,
    integrations,
    knowledge,
    knowledge_base,
    knowledge_graph,
    learning,
    learning_events,
    lsv,
    model_gateway,
    module_ai,
    plan,
    prompt_center,
    psychology,
    rag,
    risks,
    risk_forecast,
    schedule,
    simulation,
    skill_market,
    social,
    stream,
    study_tools,
    tutor,
    teacher,
)
from .cache import cache
from .config import settings
from .database import (
    ACTIVE_DATABASE_BACKEND,
    ACTIVE_DATABASE_URL,
    DATABASE_ERROR,
    DATABASE_FALLBACK,
    Base,
    SessionLocal,
    engine,
)
from .llm import llm
from .prompts.registry import sync_prompt_versions

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

FRONTEND_DIST = Path(settings.FRONTEND_DIST)
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("xueji")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False


def ensure_schema() -> None:
    """建表并为旧数据库补充新增列，SQLite 与 MySQL 通用。"""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    def add_columns(table: str, columns: dict) -> None:
        if table not in tables:
            return
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name in existing:
                continue
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

    add_columns(
        "mistakes",
        {
            "image_url": "VARCHAR(255)",
            "distractor_cause": "VARCHAR(32)",
        },
    )
    add_columns(
        "goals",
        {
            "force_mode": "BOOLEAN DEFAULT 0",
            "min_daily_minutes": "INTEGER DEFAULT 30",
            "camera_required": "BOOLEAN DEFAULT 0",
        },
    )
    add_columns(
        "users",
        {
            # 平台超级管理员（开发者账号）：老库补列，默认 False
            "is_superadmin": "BOOLEAN DEFAULT 0",
        },
    )
    add_columns(
        "tasks",
        {
            "skip_reason": "VARCHAR(255)",
            "feedback": "VARCHAR(16)",
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with SessionLocal() as db:
            sync_prompt_versions(db)
            from .services.eval_cases import seed_eval_cases

            seed_eval_cases(db)
    except Exception:  # noqa: BLE001 - 提示词/用例初始化失败不阻断启动
        logger.warning("提示词版本或用例同步失败，已跳过", exc_info=True)
    logger.info(
        "启动完成 | database=%s fallback=%s cache=%s llm=%s",
        ACTIVE_DATABASE_BACKEND,
        DATABASE_FALLBACK,
        cache.backend,
        llm.available,
    )
    if DATABASE_FALLBACK:
        logger.warning("云数据库降级运行：%s", DATABASE_ERROR)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="以学习状态数据为核心的自适应 AI 学习教练：生成、执行、反馈、重排的闭环。",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cache_control(request: Request, call_next):
    """入口 HTML 不缓存，带内容哈希的静态资源长缓存，避免旧样式被浏览器复用。"""
    response = await call_next(request)
    path = request.url.path
    suffix = path.rsplit("/", 1)[-1]
    if "/assets/" in path or "." in suffix:
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "请求异常 %s %s request_id=%s", request.method, request.url.path, request_id
        )
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-Id"] = request_id
    latency = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "%s %s -> %s %sms trace_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        latency,
        request_id,
    )
    return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or "unknown"


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("数据库异常 %s %s request_id=%s", request.method, request.url.path, _request_id(request))
    return JSONResponse(
        status_code=503,
        content={"detail": "数据库暂不可用，请检查云数据库状态或稍后重试", "request_id": _request_id(request)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("未处理异常 %s %s request_id=%s", request.method, request.url.path, _request_id(request))
    return JSONResponse(
        status_code=500,
        content={"detail": "服务内部错误，已记录日志", "request_id": _request_id(request)},
    )

for module in (
    auth,
    goals,
    commitment,
    plan,
    psychology,
    learning,
    learning_events,
    lsv,
    module_ai,
    model_gateway,
    dashboard,
    admin,
    entertainment,
    eval_center,
    family,
    social,
    coach,
    skill_market,
    focus,
    insights,
    study_tools,
    tutor,
    teacher,
    integrations,
    cockpit,
    knowledge,
    knowledge_base,
    knowledge_graph,
    simulation,
    prompt_center,
    stream,
    risks,
    schedule,
    rag,
    experiments,
    ai_lab,
    advanced,
    evidence,
    risk_forecast,
    cloud_services,
    vocab,
    teaching,
    exam_prep,
    media_proxy,
):
    app.include_router(module.router, prefix=settings.API_PREFIX)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "degraded" if DATABASE_FALLBACK else "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "database": ACTIVE_DATABASE_BACKEND,
        "database_fallback": DATABASE_FALLBACK,
        "database_error": DATABASE_ERROR[:120] if DATABASE_ERROR else "",
        "cache": cache.backend,
        "llm": llm.available,
    }


if UPLOAD_DIR.exists():
    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
else:
    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR), check_dir=False), name="uploads")

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="web")