import os
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _build_database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    host = _first_env("RDS_INTRANET_HOST", "RDS_HOST", "HUAWEI_RDS_HOST")
    if host and (not configured or configured.startswith("sqlite")):
        user = quote(_first_env("RDS_USER", default="xueji"))
        password = quote(_first_env("RDS_PASSWORD", default=""))
        port = _first_env("RDS_PORT", default="3306")
        database = _first_env("RDS_DATABASE", default="xueji")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    if configured:
        return configured
    return f"sqlite:///{(BASE_DIR / 'xueji.db').as_posix()}"


def _build_redis_url() -> str:
    configured = os.getenv("REDIS_URL", "").strip()
    if configured:
        return configured
    host = _first_env("REDIS_INTRANET_HOST", "REDIS_HOST", "DCS_HOST")
    if not host:
        return ""
    password = _first_env("REDIS_PASSWORD", "DCS_PASSWORD")
    port = _first_env("REDIS_PORT", "DCS_PORT", default="6379")
    database = _first_env("REDIS_DB", default="0")
    ssl_enabled = _first_env("REDIS_SSL", default="false").lower() in ("1", "true", "yes")
    scheme = "rediss" if ssl_enabled else "redis"
    auth = f":{quote(password)}@" if password else ""
    return f"{scheme}://{auth}{host}:{port}/{database}"


def _load_env_files() -> None:
    """读取 .env.cloud 与 .env，不覆盖外部已设置的环境变量。

    .env.cloud 优先加载，便于云连接参数覆盖本地开发配置。
    """
    for candidate in (
        BASE_DIR / ".env.cloud",
        BASE_DIR.parent / ".env.cloud",
        BASE_DIR.parent / ".env",
        BASE_DIR / ".env",
    ):
        if not candidate.exists():
            continue
        try:
            for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
        except Exception:
            continue


_load_env_files()


class Settings:
    APP_NAME = "学迹 · 自适应 AI 学习教练"
    VERSION = "1.0.0"
    API_PREFIX = "/api"

    SECRET_KEY = os.getenv("SECRET_KEY", "xueji-dev-secret-please-change")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

    # 演示账号提示：默认留空 —— 商用部署的登录页不展示任何账号密码。
    # 演示环境（如给评审/客户试用）在 .env 里写 DEMO_HINT=demo / <密码> 才会显示。
    DEMO_HINT = os.getenv("DEMO_HINT", "").strip()

    DATABASE_URL = _build_database_url()
    REDIS_URL = _build_redis_url()

    CLOUD_REGION = os.getenv("CLOUD_REGION", "cn-north-4")
    CLOUD_PROJECT_ID = os.getenv("CLOUD_PROJECT_ID", "")
    CLOUD_ACCESS_KEY = os.getenv("HUAWEICLOUD_SDK_AK", "")
    CLOUD_SECRET_KEY = os.getenv("HUAWEICLOUD_SDK_SK", "")
    CLOUD_VPC_ID = os.getenv("CLOUD_VPC_ID", "")
    CLOUD_SUBNET_ID = os.getenv("CLOUD_SUBNET_ID", "")
    CLOUD_SECURITY_GROUP_ID = os.getenv("CLOUD_SECURITY_GROUP_ID", "")

    RDS_HOST = _first_env("RDS_HOST", "HUAWEI_RDS_HOST")
    RDS_INTRANET_HOST = os.getenv("RDS_INTRANET_HOST", "")
    RDS_PORT = _first_env("RDS_PORT", default="3306")
    RDS_DATABASE = _first_env("RDS_DATABASE", default="xueji")
    RDS_SSL_CA = os.getenv("RDS_SSL_CA", "")

    REDIS_HOST = _first_env("REDIS_HOST", "DCS_HOST")
    REDIS_INTRANET_HOST = os.getenv("REDIS_INTRANET_HOST", "")
    REDIS_PORT = _first_env("REDIS_PORT", "DCS_PORT", default="6379")
    REDIS_SSL_CA = os.getenv("REDIS_SSL_CA", "")

    OBS_ENDPOINT = os.getenv("OBS_ENDPOINT", "")
    OBS_BUCKET = os.getenv("OBS_BUCKET", "")
    OBS_ACCESS_KEY = os.getenv("OBS_ACCESS_KEY", os.getenv("HUAWEICLOUD_SDK_AK", ""))
    OBS_SECRET_KEY = os.getenv("OBS_SECRET_KEY", os.getenv("HUAWEICLOUD_SDK_SK", ""))
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")

    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "pangu")
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "25"))
    QUESTION_BANK_API_URL = os.getenv("QUESTION_BANK_API_URL", "").strip()
    QUESTION_BANK_API_KEY = os.getenv("QUESTION_BANK_API_KEY", "")
    QUESTION_BANK_TIMEOUT = float(os.getenv("QUESTION_BANK_TIMEOUT", "8"))
    # 出题优先级：True = 在线题库/模型优先，内置题库兜底；False = 旧行为（内置题库优先）
    QUIZ_LIVE_FIRST = os.getenv("QUIZ_LIVE_FIRST", "true").lower() in ("1", "true", "yes", "on")
    # 在线取题的等待上限，超时立即退回内置题库，避免出题卡住
    QUIZ_LIVE_TIMEOUT = float(os.getenv("QUIZ_LIVE_TIMEOUT", "12"))

    # ===== 第三方查题题库（柠檬题库 lemtk / LIKE知识库 datam.site 同款查题接口）=====
    # 文档: https://docs.lemtk.xyz/get-started.html
    # 普通查询 /api/v1/cx（Token 可选，免费但限流）；高级查询 /api/v1/mcx（Token 必填）
    # 余额查询 GET /api/v1/balance?email=&token=
    QBANK_BASE_URL = (
        os.getenv("QBANK_BASE_URL", "").strip()
        or QUESTION_BANK_API_URL  # 向后兼容旧配置
    )
    QBANK_TOKEN = (
        os.getenv("QBANK_TOKEN", "").strip()
        or QUESTION_BANK_API_KEY  # 向后兼容旧配置
    )
    QBANK_EMAIL = os.getenv("QBANK_EMAIL", "").strip()
    QBANK_MODE = os.getenv("QBANK_MODE", "cx").strip().lower()
    QBANK_TIMEOUT = float(os.getenv("QBANK_TIMEOUT", str(QUESTION_BANK_TIMEOUT)))
    # 查题题库供应商: lemtk(柠檬题库，默认) / gomooc(ZERO 网课题库)
    QBANK_PROVIDER = os.getenv("QBANK_PROVIDER", "lemtk").strip().lower()

    # ===== ZERO 网课题库（https://api.gomooc.net/api.php）=====
    # 接口: GET /api.php?token=<token>&question=<题干>；无 token 不可用，额度耗尽返回 code 429
    QBANK_GOMOOC_BASE_URL = (
        os.getenv("QBANK_GOMOOC_BASE_URL", "").strip() or "https://api.gomooc.net"
    )
    QBANK_GOMOOC_ENDPOINT = os.getenv("QBANK_GOMOOC_ENDPOINT", "/api.php").strip() or "/api.php"
    QBANK_GOMOOC_TOKEN = (
        os.getenv("QBANK_GOMOOC_TOKEN", "").strip()
        or os.getenv("QBANK_TOKEN", "").strip()  # 只有 ZERO 启用时才复用通用 Token
    )
    # 首轮未命中时，是否把选项拼进题干再查一次
    QBANK_GOMOOC_MERGE_OPTIONS = os.getenv(
        "QBANK_GOMOOC_MERGE_OPTIONS", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    # 主供应商不可用时（额度用尽 / Token 无效 / 超时）自动回落的备用供应商，留空表示不降级
    QBANK_FALLBACK_PROVIDER = os.getenv("QBANK_FALLBACK_PROVIDER", "").strip().lower()

    # ===== 视频课程检索（多源）=====
    # B 站公开搜索接口始终启用（无需密钥）；
    # YouTube Data API v3 为可选源：配置密钥后自动加入聚合，
    # 未配置时在来源状态中如实标注 not_configured，不影响其他源。
    VIDEO_YOUTUBE_API_KEY = os.getenv("VIDEO_YOUTUBE_API_KEY", os.getenv("YOUTUBE_API_KEY", "")).strip()
    VIDEO_YOUTUBE_REGION = os.getenv("VIDEO_YOUTUBE_REGION", "US").strip() or "US"
    VIDEO_TIMEOUT = float(os.getenv("VIDEO_TIMEOUT", "8"))

    # ===== 自建题库（tikuAdapter）：按知识点建课程，出题前先从这里取题 =====
    # 部署见 external/tikuAdapter；课程名 = 知识点名，做到「题与知识点一一对应」
    TIKU_ADAPTER_URL = os.getenv("TIKU_ADAPTER_URL", "").strip().rstrip("/")
    TIKU_ADAPTER_USER = os.getenv("TIKU_ADAPTER_USER", "admin").strip()
    TIKU_ADAPTER_PASSWORD = os.getenv("TIKU_ADAPTER_PASSWORD", "123456")
    TIKU_ADAPTER_TIMEOUT = float(os.getenv("TIKU_ADAPTER_TIMEOUT", "6"))
    LLM_PRIMARY = os.getenv("LLM_PRIMARY", "deepseek")
    MAAS_BASE_URL = os.getenv("MAAS_BASE_URL", "")
    MAAS_API_KEY = os.getenv("MAAS_API_KEY", "")
    MAAS_MODEL = os.getenv("MAAS_MODEL", "")
    OCR_ENDPOINT = os.getenv("OCR_ENDPOINT", "")
    OCR_API_KEY = os.getenv("OCR_API_KEY", "")
    SIS_ENDPOINT = os.getenv("SIS_ENDPOINT", "")
    SIS_API_KEY = os.getenv("SIS_API_KEY", "")
    LLM_FAILURE_THRESHOLD = int(os.getenv("LLM_FAILURE_THRESHOLD", "3"))
    LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "60"))
    LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "")
    LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "")
    LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "")
    # 文档 6.4 / 附录 C：档位路由与调用预算，模型名由配置决定，不写死在代码里
    LLM_TIER_FAST = os.getenv("LLM_TIER_FAST", "")
    LLM_TIER_GENERAL = os.getenv("LLM_TIER_GENERAL", "")
    LLM_TIER_REASONING = os.getenv("LLM_TIER_REASONING", "")
    LLM_DAILY_TOKEN_BUDGET = int(os.getenv("LLM_DAILY_TOKEN_BUDGET", "0"))
    LLM_AUDIT_ENABLED = os.getenv("LLM_AUDIT_ENABLED", "true").lower() in ("1", "true", "yes", "on")

    CORS_ORIGINS = [
        item.strip()
        for item in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
        ).split(",")
        if item.strip()
    ]

    MAX_UPLOAD_BYTES = 5 * 1024 * 1024
    MAX_DAILY_TASKS = 5

    FRONTEND_DIST = os.getenv(
        "FRONTEND_DIST",
        str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"),
    )

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))


settings = Settings()
