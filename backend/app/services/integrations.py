"""网络与模型接入状态：统一检查 DeepSeek、数据库、缓存、存储与浏览器能力。"""

import time
import uuid
from pathlib import Path
from typing import Dict, List

from sqlalchemy import text

from ..cache import cache
from ..config import settings
from ..database import (
    ACTIVE_DATABASE_BACKEND,
    ACTIVE_DATABASE_URL,
    DATABASE_ERROR,
    DATABASE_FALLBACK,
    engine,
)
from ..llm import llm
from . import knowledge_base


def _base_host() -> str:
    url = settings.LLM_BASE_URL
    if "://" in url:
        return url.split("://", 1)[1].split("/", 1)[0]
    return url or ""


def describe_video_sources() -> str:
    """多源视频检索的状态描述：如实列出每个源的启用情况。"""
    from .video_search import available_sources

    sources = available_sources()
    enabled = [s["label"] for s in sources if s["configured"]]
    disabled = [s["label"] for s in sources if not s["configured"]]
    parts = []
    if enabled:
        parts.append("已启用：" + "、".join(enabled))
    if disabled:
        parts.append("未配置：" + "、".join(disabled))
    return "多源聚合检索（" + "；".join(parts) + "）"


def _database_detail() -> str:
    if ACTIVE_DATABASE_BACKEND == "rds":
        return (
            f"华为云 RDS MySQL · {settings.RDS_HOST}:{settings.RDS_PORT}/"
            f"{settings.RDS_DATABASE} · {settings.CLOUD_REGION}"
        )
    if ACTIVE_DATABASE_BACKEND == "sqlite-fallback":
        return f"RDS 不可达，已自动回退本地 SQLite · {DATABASE_ERROR[:80]}"
    return "SQLite（开发模式，未接入 RDS）"


def _cache_detail() -> str:
    if cache.backend == "redis":
        return f"华为云 DCS Redis · {settings.REDIS_HOST or '已配置'}:{settings.REDIS_PORT} · {settings.CLOUD_REGION}"
    return "内存缓存（未接入 DCS Redis；DCS 公网暂不可达）"


def _database_status() -> str:
    """描述数据库配置状态：RDS 正常 / SQLite 降级 / 本地开发。"""
    if ACTIVE_DATABASE_BACKEND == "sqlite-fallback":
        return "degraded"
    if ACTIVE_DATABASE_BACKEND == "rds":
        return "ok"
    return "not_configured"


def describe_integrations() -> Dict:
    kb = knowledge_base.describe()
    question_bank_url = getattr(settings, "QBANK_BASE_URL", "") or getattr(
        settings, "QUESTION_BANK_API_URL", ""
    )
    qbank_token_configured = bool(getattr(settings, "QBANK_TOKEN", "") or getattr(settings, "QUESTION_BANK_API_KEY", ""))
    items = [
        {
            "key": "deepseek",
            "name": "DeepSeek 模型接口",
            "type": "model",
            "configured": llm.available,
            "detail": f"{settings.LLM_MODEL} · {_base_host() or '未配置地址'}",
        },
        {
            "key": "question_bank",
            "name": "外部查题题库 API",
            "type": "network",
            "configured": bool(question_bank_url),
            "status": "unknown" if question_bank_url else "not_configured",
            "detail": (
                f"已配置题库域名（{'高级查询' if getattr(settings, 'QBANK_MODE', 'cx') == 'mcx' else '普通查询'}，"
                f"{'Token 已配置' if qbank_token_configured else '未配置 Token，走免费限流通道'}）；密钥不会下发到浏览器"
                if question_bank_url
                else "未配置外部题库 API；当前使用内置题库，未覆盖时再按模型/规则降级"
            ),
        },
        {
            "key": "video_sources",
            "name": "视频课程检索（多源）",
            "type": "network",
            "configured": True,
            "status": "ok",
            "detail": describe_video_sources(),
        },
        {
            "key": "database",
            "name": "业务数据库（RDS）",
            "type": "cloud",
            "configured": ACTIVE_DATABASE_BACKEND == "rds",
            "status": _database_status(),
            "detail": _database_detail(),
        },
        {
            "key": "cache",
            "name": "分布式缓存（DCS Redis）",
            "type": "cloud",
            "configured": cache.backend == "redis",
            "detail": _cache_detail(),
        },
        {
            "key": "storage",
            "name": "文件存储",
            "type": "network",
            "configured": True,
            "detail": settings.UPLOAD_DIR,
        },
        {
            "key": "speech",
            "name": "语音识别 / 合成",
            "type": "browser",
            "configured": bool(getattr(settings, "SIS_ENDPOINT", "")),
            "status": "ok" if getattr(settings, "SIS_ENDPOINT", "") else "degraded",
            "detail": "华为云 SIS 未配置，当前使用浏览器 Web Speech API 降级（Chrome / Edge）",
            "cloud": "华为云 SIS",
        },
        {
            "key": "camera",
            "name": "摄像头",
            "type": "browser",
            "configured": True,
            "status": "ok",
            "detail": "端侧在场判断，默认不上传原图",
        },
        {
            "key": "ocr",
            "name": "错题 OCR",
            "type": "network",
            "configured": bool(getattr(settings, "OCR_ENDPOINT", "")),
            "status": "ok" if getattr(settings, "OCR_ENDPOINT", "") else "not_configured",
            "detail": "华为云 OCR 未配置，当前错题拍照使用手动录入降级",
            "cloud": "华为云 OCR",
        },
        {
            "key": "sis",
            "name": "语音 SIS",
            "type": "network",
            "configured": bool(getattr(settings, "SIS_ENDPOINT", "")),
            "status": "ok" if getattr(settings, "SIS_ENDPOINT", "") else "not_configured",
            "detail": "华为云 SIS 未配置，语音能力由浏览器原生能力降级提供",
            "cloud": "华为云 SIS",
        },
        {
            "key": "external",
            "name": "外部知识库",
            "type": "network",
            "configured": kb["configured"],
            "status": kb["status"],
            "detail": kb["detail"],
            "sources": kb["sources"],
        },
    ]
    degraded_count = len([item for item in items if item.get("status") == "degraded"])
    return {
        "items": items,
        "status": "degraded" if degraded_count else "ok",
        "degraded_count": degraded_count,
        "configured_count": len([item for item in items if item["configured"]]),
        "total": len(items),
    }


async def _test_deepseek() -> Dict:
    if not llm.available:
        return {"status": "not_configured", "latency_ms": None, "detail": "未配置 LLM_API_KEY"}
    start = time.perf_counter()
    text = await llm.chat("只回复 OK", "ping", temperature=0, max_tokens=5)
    latency = round((time.perf_counter() - start) * 1000)
    if text:
        return {"status": "ok", "latency_ms": latency, "detail": f"模型回复：{text.strip()[:20]}"}
    return {"status": "error", "latency_ms": latency, "detail": "调用失败，已自动回退规则引擎"}


def _test_database() -> Dict:
    start = time.perf_counter()
    try:
        with engine.connect() as connection:
            if ACTIVE_DATABASE_BACKEND == "rds":
                value = connection.execute(text("SELECT VERSION()")).scalar()
            else:
                value = connection.execute(text("SELECT sqlite_version()")).scalar()
        if ACTIVE_DATABASE_BACKEND == "sqlite-fallback":
            return {
                "status": "degraded",
                "latency_ms": round((time.perf_counter() - start) * 1000),
                "detail": f"RDS 不可达，已回退 SQLite {str(value)[:20]}",
            }
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "detail": f"连接正常 · {str(value)[:40]}",
        }
    except Exception as exc:
        return {"status": "error", "latency_ms": None, "detail": str(exc)[:120]}


def _test_cache() -> Dict:
    start = time.perf_counter()
    try:
        key = f"integration:ping:{uuid.uuid4().hex[:8]}"
        cache.set_json(key, {"ok": True}, ttl=10)
        value = cache.get_json(key)
        cache.delete(key)
        ok = bool(value and value.get("ok"))
        info = cache.info()
        if cache.backend == "redis":
            detail = (
                f"Redis {info.get('version', '')} 读写正常 · "
                f"内存 {info.get('used_memory_human', '')}"
            )
        else:
            detail = "进程内存缓存读写正常，未接入 DCS Redis"
        if cache.backend != "redis":
            return {
                "status": "degraded" if ok else "error",
                "latency_ms": round((time.perf_counter() - start) * 1000),
                "detail": detail.strip(),
            }
        return {
            "status": "ok" if ok else "error",
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "detail": detail.strip(),
        }
    except Exception as exc:
        return {"status": "error", "latency_ms": None, "detail": str(exc)[:120]}


def _test_storage() -> Dict:
    start = time.perf_counter()
    try:
        folder = Path(settings.UPLOAD_DIR) / "_health"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{uuid.uuid4().hex}.txt"
        target.write_text("ok", encoding="utf-8")
        content = target.read_text(encoding="utf-8")
        target.unlink()
        return {
            "status": "ok" if content == "ok" else "error",
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "detail": "读写正常",
        }
    except Exception as exc:
        return {"status": "error", "latency_ms": None, "detail": str(exc)[:120]}


TEST_CACHE_TTL = 20
_integration_test_cache: Dict = {"at": 0.0, "results": None}


async def test_integrations(force: bool = False) -> List[Dict]:
    if (
        not force
        and _integration_test_cache["results"] is not None
        and time.time() - _integration_test_cache["at"] < TEST_CACHE_TTL
    ):
        return _integration_test_cache["results"]

    described = describe_integrations()["items"]
    results = []
    for item in described:
        key = item["key"]
        if key == "deepseek":
            result = await _test_deepseek()
        elif key == "database":
            result = _test_database()
        elif key == "cache":
            result = _test_cache()
        elif key == "storage":
            result = _test_storage()
        elif key in ("speech", "camera"):
            result = {
                "status": "client",
                "latency_ms": None,
                "detail": "由浏览器提供，需在页面中授权",
            }
        elif key == "question_bank":
            result = {
                "status": "unknown" if item["configured"] else "not_configured",
                "latency_ms": None,
                "detail": (
                    "已配置；为避免产生计费请求，集成页不主动调用题库，首次实际出题时验证并自动缓存"
                    if item["configured"]
                    else item["detail"]
                ),
            }
        elif key == "video_sources":
            from .video_search import available_sources

            sources = available_sources()
            enabled = [s["label"] for s in sources if s["configured"]]
            result = {
                "status": "ok" if enabled else "not_configured",
                "latency_ms": None,
                "detail": (
                    "已启用 " + "、".join(enabled) + "（聚合检索在用户触发时验证，结果按关键词缓存）"
                    if enabled
                    else "没有已启用的视频来源"
                ),
            }
        elif key == "external":
            sources = await knowledge_base.probe(force=True)
            available = len([source for source in sources if source["status"] == "ok"])
            latencies = [source["latency_ms"] for source in sources if source["latency_ms"] is not None]
            result = {
                "status": "ok" if available else "unavailable",
                "latency_ms": min(latencies) if latencies else None,
                "detail": f"已连通 {available}/{len(sources)} 个来源 · "
                + " · ".join(source["name"] for source in sources if source["status"] == "ok"),
                "sources": sources,
            }
        else:
            result = {
                "status": "unavailable",
                "latency_ms": None,
                "detail": item["detail"],
            }
        results.append({**item, **result})
    _integration_test_cache["results"] = results
    _integration_test_cache["at"] = time.time()
    return results
