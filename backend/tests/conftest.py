import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

TMP_DIR = BASE_DIR / ".pytest-tmp"
TMP_DIR.mkdir(exist_ok=True)
DB_FILE = TMP_DIR / "test.db"

# 测试必须完全隔离外部云服务：先清空 .env.cloud / .env 中的真实连接参数，
# 否则 config._build_database_url() 会因 RDS_HOST 存在而覆盖 DATABASE_URL，
# 导致单元测试启动时真的去连华为云 RDS。
for _cloud_key in (
    "RDS_HOST",
    "HUAWEI_RDS_HOST",
    "RDS_PORT",
    "RDS_USER",
    "RDS_PASSWORD",
    "RDS_DATABASE",
    "RDS_SSL_CA",
    "REDIS_HOST",
    "DCS_HOST",
    "REDIS_PORT",
    "REDIS_PASSWORD",
    "DCS_PASSWORD",
    "REDIS_SSL_CA",
):
    os.environ[_cloud_key] = ""
os.environ["XUEJI_TESTING"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ["REDIS_URL"] = ""
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
# 自建题库（tikuAdapter）默认不在单测里连接：需要它的用例自己 monkeypatch 打开
os.environ["TIKU_ADAPTER_URL"] = ""
os.environ["FRONTEND_DIST"] = str(BASE_DIR.parent / "frontend" / "dist")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.cache import cache  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Goal, KnowledgePoint, User  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    """每个用例使用全新的库表与空缓存，保证互不影响。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    cache._fallback._data.clear()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def forbid_real_cloud_connections():
    """硬性保证任何用例都不会连接真实 RDS / DCS Redis。

    与 disable_real_llm 配合，确保测试环境只使用内存 SQLite 与内存缓存。
    若环境变量泄漏导致接入了真实云服务，直接让用例失败而不是静默出网。
    """
    from app import database as database_module
    from app.cache import cache as app_cache
    from app.config import settings as app_settings

    assert app_settings.DATABASE_URL.startswith("sqlite"), "测试不得连接真实 RDS"
    assert app_settings.RDS_HOST == "", "测试不得加载 RDS_HOST"
    assert database_module.ACTIVE_DATABASE_BACKEND == "sqlite", "测试数据库必须是本地 SQLite"
    assert database_module.DATABASE_FALLBACK is False, "测试不应触发 RDS 降级探活"
    assert app_settings.REDIS_URL == "", "测试不得连接真实 DCS Redis"
    assert app_cache._redis is None, "测试缓存必须是内存实现"
    assert app_settings.TIKU_ADAPTER_URL == "", "测试不得连接真实题库服务"
    yield


@pytest.fixture(autouse=True)
def disable_real_llm(monkeypatch):
    """单元测试强制禁用真实 LLM 调用。

    根目录 .env 可能配置了 DeepSeek 密钥，但测试环境必须在导入 app 前把
    LLM_BASE_URL / LLM_API_KEY 置空，避免消耗额度并保证结果稳定。
    这里再做一次防御性断言与实例清理，任何测试都不会发出真实外网请求。
    """
    from app import llm as llm_module
    from app.config import settings as app_settings

    assert app_settings.LLM_BASE_URL == "", "测试环境不应加载 LLM_BASE_URL（会触发真实调用）"
    assert app_settings.LLM_API_KEY == "", "测试环境不应加载 LLM_API_KEY（会触发真实调用）"

    monkeypatch.setattr(llm_module.llm, "base_url", "")
    monkeypatch.setattr(llm_module.llm, "api_key", "")
    assert llm_module.llm.available is False
    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api():
    """同步调用异步 ASGI 应用的轻量客户端（starlette TestClient 与 httpx 0.28 不兼容）。"""

    def call(method, path, token=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params = kwargs.pop("params", None)

        async def _run():
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, path, headers=headers, params=params, **kwargs)

        return asyncio.run(_run())

    return call


@pytest.fixture()
def auth(api):
    response = api(
        "POST",
        "/api/auth/register",
        json={"username": "tester", "password": "secret123", "nickname": "测试同学"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {"token": payload["access_token"], "user": payload["user"]}


@pytest.fixture()
def goal(api, auth):
    response = api(
        "POST",
        "/api/goals",
        token=auth["token"],
        json={
            "exam_name": "大学英语四级",
            "exam_date": (date.today() + timedelta(days=40)).isoformat(),
            "daily_minutes": 90,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


MATERIAL = """# 听力
- 短对话
- 长对话
- 听力篇章

# 阅读
- 选词填空
- 仔细阅读

# 写作
- 议论文结构
- 常用句型
"""


@pytest.fixture()
def imported_points(api, auth, goal):
    response = api(
        "POST",
        f"/api/goals/{goal['id']}/materials/text",
        token=auth["token"],
        json={"filename": "四级大纲", "content": MATERIAL},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def db_user_goal(db):
    """不经过接口，直接构造用户与目标，供规则层单元测试使用。"""
    user = User(username="direct", password_hash=hash_password("secret123"), nickname="小林")
    db.add(user)
    db.flush()
    goal = Goal(
        user_id=user.id,
        exam_name="CET-4",
        exam_date=date.today() + timedelta(days=30),
        daily_minutes=90,
    )
    db.add(goal)
    db.flush()
    db.commit()
    return user, goal


def add_points(db, goal, names=("听力", "阅读", "写作")):
    created = []
    for index, name in enumerate(names):
        point = KnowledgePoint(goal_id=goal.id, name=name, weight=1.0 + index * 0.5)
        db.add(point)
        db.flush()
        created.append(point)
    db.commit()
    return created