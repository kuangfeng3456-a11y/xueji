"""外部知识库接入：OpenAlex（学术图谱）、Crossref（文献元数据）、百度百科（中文百科）。

三个来源均为真实外网 HTTP 接口，已在本机实测可达；维基百科类域名当前不可达，不纳入。
探测结果缓存 90 秒，供接入中心同步展示。
"""

import asyncio
import time
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx

TIMEOUT = 8.0
HEADERS = {"User-Agent": "Xueji/1.0 (adaptive learning coach)"}

SOURCES: List[Dict] = [
    {
        "key": "openalex",
        "name": "OpenAlex",
        "kind": "学术知识图谱",
        "base": "https://api.openalex.org",
        "home": "https://openalex.org",
        "probe": "/works?search=learning&per-page=1",
    },
    {
        "key": "crossref",
        "name": "Crossref",
        "kind": "文献元数据",
        "base": "https://api.crossref.org",
        "home": "https://search.crossref.org",
        "probe": "/works?query=learning&rows=1",
    },
    {
        "key": "baidu",
        "name": "百度百科",
        "kind": "中文百科词条",
        "base": "https://baike.baidu.com",
        "home": "https://baike.baidu.com",
        "probe": "/api/openapi/BaikeLemmaCardApi?scope=103&format=json&appid=379020&bk_key="
        + quote("机器学习"),
    },
]

SOURCE_MAP = {source["key"]: source for source in SOURCES}
CACHE_TTL = 90
_last_probe: Dict = {"at": 0.0, "results": []}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True, trust_env=False)


def describe() -> Dict:
    """同步返回最近一次探测摘要，供接入中心首屏展示。"""
    results = _last_probe["results"]
    if not results:
        return {
            "configured": True,
            "status": "unknown",
            "detail": "OpenAlex · Crossref · 百度百科（待测试）",
            "sources": [
                {"key": s["key"], "name": s["name"], "kind": s["kind"], "status": "unknown", "latency_ms": None, "detail": "待测试"}
                for s in SOURCES
            ],
        }
    ok = [item for item in results if item["status"] == "ok"]
    names = " · ".join(item["name"] for item in ok) or "无可用源"
    return {
        "configured": bool(ok),
        "status": "ok" if ok else "unavailable",
        "detail": f"已连通 {len(ok)}/{len(results)} 个来源：{names}",
        "sources": results,
    }


async def probe(force: bool = False) -> List[Dict]:
    if not force and _last_probe["results"] and time.time() - _last_probe["at"] < CACHE_TTL:
        return _last_probe["results"]

    async with _client() as client:
        results = await asyncio.gather(*(_probe_one(client, source) for source in SOURCES))
    _last_probe["results"] = list(results)
    _last_probe["at"] = time.time()
    return _last_probe["results"]


def _error_text(exc: Exception) -> str:
    detail = f"{type(exc).__name__}: {exc}".strip()
    return detail[:120] or type(exc).__name__


async def _probe_one(client: httpx.AsyncClient, source: Dict) -> Dict:
    start = time.perf_counter()
    try:
        resp = await client.get(source["base"] + source["probe"])
        latency = round((time.perf_counter() - start) * 1000)
        ok = 200 <= resp.status_code < 400
        size = round(len(resp.content) / 1024, 1)
        return {
            "key": source["key"],
            "name": source["name"],
            "kind": source["kind"],
            "status": "ok" if ok else "error",
            "latency_ms": latency,
            "detail": f"HTTP {resp.status_code} · {size} KB",
            "link": source["home"],
        }
    except Exception as exc:
        return {
            "key": source["key"],
            "name": source["name"],
            "kind": source["kind"],
            "status": "error",
            "latency_ms": None,
            "detail": _error_text(exc),
            "link": source["home"],
        }


def _empty(source_key: str, status: str, summary: str) -> Dict:
    source = SOURCE_MAP[source_key]
    return {
        "key": source_key,
        "name": source["name"],
        "kind": source["kind"],
        "status": status,
        "latency_ms": None,
        "summary": summary,
        "link": source["home"],
    }


def _abstract(inverted: Optional[Dict]) -> str:
    if not inverted:
        return ""
    positions = []
    for word, indexes in inverted.items():
        for index in indexes or []:
            positions.append((index, word))
    positions.sort()
    return " ".join(word for _, word in positions)


async def _lookup_openalex(client: httpx.AsyncClient, term: str) -> Dict:
    start = time.perf_counter()
    try:
        resp = await client.get(
            SOURCE_MAP["openalex"]["base"] + "/works",
            params={"search": term, "per-page": 1},
        )
        latency = round((time.perf_counter() - start) * 1000)
        resp.raise_for_status()
        results = (resp.json() or {}).get("results") or []
        if not results:
            return {**_empty("openalex", "empty", "未检索到相关学术条目"), "latency_ms": latency}
        work = results[0]
        title = work.get("display_name") or ""
        abstract = _abstract(work.get("abstract_inverted_index"))
        link = (
            (work.get("primary_location") or {}).get("landing_page_url")
            or work.get("doi")
            or SOURCE_MAP["openalex"]["home"]
        )
        cited = (work.get("cited_by_count") or 0)
        summary = f"{title}：{abstract}"[:420] if abstract else f"{title}（被引 {cited} 次）"[:420]
        return {**_empty("openalex", "ok", summary or "已连通，条目暂无摘要"), "latency_ms": latency, "link": link}
    except Exception as exc:
        return _empty("openalex", "error", _error_text(exc))


async def _lookup_crossref(client: httpx.AsyncClient, term: str) -> Dict:
    start = time.perf_counter()
    try:
        resp = await client.get(
            SOURCE_MAP["crossref"]["base"] + "/works",
            params={"query": term, "rows": 1},
        )
        latency = round((time.perf_counter() - start) * 1000)
        resp.raise_for_status()
        items = ((resp.json() or {}).get("message") or {}).get("items") or []
        if not items:
            return {**_empty("crossref", "empty", "未检索到相关文献"), "latency_ms": latency}
        item = items[0]
        title = (item.get("title") or [""])[0]
        container = (item.get("container-title") or [""])[0]
        year = ((item.get("issued") or {}).get("date-parts") or [[""]])[0][0]
        doi = item.get("DOI") or ""
        link = f"https://doi.org/{doi}" if doi else SOURCE_MAP["crossref"]["home"]
        summary = f"{title}（{container} {year}）" if container else f"{title}（{year}）"
        return {**_empty("crossref", "ok", summary[:420]), "latency_ms": latency, "link": link}
    except Exception as exc:
        return _empty("crossref", "error", _error_text(exc))


async def _lookup_baidu(client: httpx.AsyncClient, term: str) -> Dict:
    start = time.perf_counter()
    try:
        resp = await client.get(
            SOURCE_MAP["baidu"]["base"] + "/api/openapi/BaikeLemmaCardApi",
            params={"scope": 103, "format": "json", "appid": 379020, "bk_key": term},
        )
        latency = round((time.perf_counter() - start) * 1000)
        resp.raise_for_status()
        data = resp.json() or {}
        title = str(data.get("title") or "")
        desc = str(data.get("desc") or "")
        abstract = str(data.get("abstract") or "")
        if not title:
            return {**_empty("baidu", "empty", "未检索到相关词条"), "latency_ms": latency}
        summary = f"{title}：{desc or abstract}" if (desc or abstract) else title
        link = f"https://baike.baidu.com/item/{quote(title)}"
        return {**_empty("baidu", "ok", summary[:420]), "latency_ms": latency, "link": link}
    except Exception as exc:
        return _empty("baidu", "error", _error_text(exc))


async def lookup(term: str) -> Dict:
    """按词条并发查询三个外部知识库，任一失败不影响其余来源。"""
    cleaned = (term or "").strip()
    async with _client() as client:
        results = await asyncio.gather(
            _lookup_baidu(client, cleaned),
            _lookup_openalex(client, cleaned),
            _lookup_crossref(client, cleaned),
        )
    available = [item for item in results if item["status"] in ("ok", "empty")]
    return {
        "term": cleaned,
        "sources": list(results),
        "available_count": len(available),
        "total": len(results),
        "status": "ok" if available else "unavailable",
    }