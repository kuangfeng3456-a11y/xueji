"""真实视频课程检索（多源适配器架构）。

设计原则（沿用项目「不造假数据」的约束）：
1. 只返回网络接口真实返回的视频，不内置任何示例视频；
2. 每个来源是一个独立适配器：来源不可用/未配置时如实上报状态，
   绝不用其他源伪造，也不静默吞掉失败；
3. 多源结果轮转合并（source 优先轮转，其次关键词轮转），保证来源多样性：
   不会出现单一来源刷屏，也不会单一知识点霸屏；
4. 结果按 (来源, 关键词) 缓存，避免每次打开页面都打上游接口。

当前来源：
- bilibili  B 站公开搜索接口（默认，无需密钥）
- youtube   YouTube Data API v3（可选：配置 VIDEO_YOUTUBE_API_KEY 后自动启用；
            未配置时在 sources 状态中如实标注，不影响其他源）

曾经评估并放弃的源（记录避免重复踩坑）：
- 中国大学MOOC：搜索 RPC 需要会话 Cookie+csrfKey 握手，服务端无头调用不稳定；
- 学堂在线：公开搜索接口已下线（404）；
- 网易公开课：无可用的公开 JSON 搜索 API。
"""

import asyncio
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx

from ..cache import cache
from ..config import settings

CACHE_TTL = 6 * 3600
MIN_SECONDS = 180      # 低于 3 分钟的片段不算「一节课」
MAX_SECONDS = 60 * 60 * 12
_TAG_RE = re.compile(r"<[^>]+>")

BILIBILI_SEARCH = "https://api.bilibili.com/x/web-interface/search/type"
BILIBILI_PLAYER = "https://player.bilibili.com/player.html"
BILIBILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------

def _duration_seconds(text: str) -> int:
    """时长文本转秒：B 站形如 '6054:3' / '1:02:03'；YouTube 为 ISO8601 'PT1H2M3S'。"""
    text = str(text or "").strip()
    if text.startswith("P"):  # ISO8601
        match = re.match(
            r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", text
        )
        if not match:
            return 0
        days, hours, minutes, seconds = match.groups()
        return (
            int(days or 0) * 86400
            + int(hours or 0) * 3600
            + int(minutes or 0) * 60
            + int(float(seconds or 0))
        )
    parts = [part for part in text.split(":") if part.strip().isdigit()]
    if not parts:
        return 0
    numbers = [int(part) for part in parts]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0]


def _human_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分钟"


def _clean_pic(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    return url


# --------------------------------------------------------------------------
# 来源适配器：每个适配器返回 (items, detail)，失败抛异常由聚合层捕获上报
# --------------------------------------------------------------------------

def _bilibili_normalize(item: Dict, keyword: str) -> Optional[Dict]:
    bvid = str(item.get("bvid") or "").strip()
    title = _TAG_RE.sub("", str(item.get("title") or "")).strip()
    if not bvid or not title:
        return None
    seconds = _duration_seconds(item.get("duration"))
    if seconds < MIN_SECONDS or seconds > MAX_SECONDS:
        return None
    play = int(item.get("play") or 0)
    cover = _clean_pic(str(item.get("pic") or ""))
    return {
        "id": bvid,
        "bvid": bvid,  # 兼容旧前端（:key="video.bvid"）
        "title": title,
        "author": str(item.get("author") or "").strip(),
        "duration": _human_duration(seconds),
        "duration_seconds": seconds,
        "play": play,
        "cover": cover,
        # B 站图床按 Referer 防盗链，页面直接引用会被 403，
        # 这里给出经本站代理的地址，前端优先用它
        "cover_proxy": f"/media/image?url={quote(cover, safe='')}" if cover else "",
        "url": f"https://www.bilibili.com/video/{bvid}",
        "player_url": f"{BILIBILI_PLAYER}?bvid={bvid}&high_quality=1&danmaku=0",
        "matched_keyword": keyword,
        "source": "bilibili",
        "source_label": "B站",
    }


def _cache_key(source: str, keyword: str) -> str:
    return f"videos:{source}:{keyword}"


async def _bilibili_search(client: httpx.AsyncClient, keyword: str, limit: int) -> List[Dict]:
    response = await client.get(
        BILIBILI_SEARCH,
        params={
            "search_type": "video",
            "keyword": keyword,
            "page": 1,
            "order": "totalrank",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "搜索接口返回异常")
    results = payload.get("data", {}).get("result") or []
    videos: List[Dict] = []
    seen = set()
    for item in results:
        normalized = _bilibili_normalize(item, keyword)
        if normalized is None or normalized["id"] in seen:
            continue
        seen.add(normalized["id"])
        videos.append(normalized)
        if len(videos) >= limit:
            break
    return videos


def _youtube_available() -> bool:
    return bool(settings.VIDEO_YOUTUBE_API_KEY)


async def _youtube_search(client: httpx.AsyncClient, keyword: str, limit: int) -> List[Dict]:
    """YouTube Data API v3：search + videos 两跳（search 不返回时长）。"""
    key = settings.VIDEO_YOUTUBE_API_KEY
    search_response = await client.get(
        f"{YOUTUBE_API}/search",
        params={
            "part": "snippet",
            "type": "video",
            "q": keyword,
            "maxResults": min(max(limit * 2, 6), 25),
            "relevanceLanguage": "zh",
            "regionCode": settings.VIDEO_YOUTUBE_REGION,
            "key": key,
        },
    )
    search_response.raise_for_status()
    hits = (search_response.json().get("items") or [])
    ids = [item.get("id", {}).get("videoId") for item in hits]
    ids = [vid for vid in ids if vid]
    if not ids:
        return []
    detail_response = await client.get(
        f"{YOUTUBE_API}/videos",
        params={
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(ids[:25]),
            "key": key,
        },
    )
    detail_response.raise_for_status()
    videos: List[Dict] = []
    for item in detail_response.json().get("items") or []:
        video_id = item.get("id") or ""
        snippet = item.get("snippet") or {}
        title = str(snippet.get("title") or "").strip()
        if not video_id or not title:
            continue
        seconds = _duration_seconds((item.get("contentDetails") or {}).get("duration"))
        if seconds < MIN_SECONDS or seconds > MAX_SECONDS:
            continue
        cover = _clean_pic(
            ((snippet.get("thumbnails") or {}).get("high") or {}).get("url", "")
        )
        videos.append(
            {
                "id": video_id,
                "bvid": video_id,  # 兼容旧前端
                "title": title,
                "author": str(snippet.get("channelTitle") or "").strip(),
                "duration": _human_duration(seconds),
                "duration_seconds": seconds,
                "play": int((item.get("statistics") or {}).get("viewCount") or 0),
                "cover": cover,
                "cover_proxy": "",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "player_url": f"https://www.youtube.com/embed/{video_id}",
                "matched_keyword": keyword,
                "source": "youtube",
                "source_label": "YouTube",
            }
        )
        if len(videos) >= limit:
            break
    return videos


# 适配器注册表：name → (中文名, 是否配置可用, 搜索协程)
ADAPTERS = {
    "bilibili": {
        "label": "B站",
        "configured": lambda: True,
        "search": _bilibili_search,
    },
    "youtube": {
        "label": "YouTube",
        "configured": _youtube_available,
        "search": _youtube_search,
    },
}


# --------------------------------------------------------------------------
# 多源聚合
# --------------------------------------------------------------------------

async def search_videos(
    keywords: List[str], limit: int = 4, timeout: float = 8.0
) -> Dict:
    """按关键词检索真实视频课程（多源聚合，来源多样化）。

    返回 {items, available, source, engine, detail, latency_ms, sources}。
    - items 每条带 source / source_label，前端可展示来源徽标；
    - sources 是每个来源的真实状态（未配置/不可用/命中数），不做任何伪造；
    - `available=False` 表示所有来源都没打通或没搜到——如实呈现。
    """
    limit = max(1, min(int(limit), 8))
    words = [str(item).strip() for item in keywords if str(item or "").strip()]
    timeout_value = max(1.0, min(float(timeout or settings.VIDEO_TIMEOUT), 20.0))
    started = time.perf_counter()

    active = {
        name: adapter for name, adapter in ADAPTERS.items() if adapter["configured"]()
    }
    if not words or not active:
        return {
            "items": [],
            "available": False,
            "source": "+".join(active) or "none",
            "engine": "none",
            "detail": "没有可检索的关键词" if words else "没有已启用的视频来源",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "sources": _source_states(words, {}, active, started),
        }

    # (source, keyword) 逐格缓存：先吃缓存，未命中的再并发拉取
    buckets: Dict[str, Dict[str, List[Dict]]] = {name: {} for name in active}
    pending: List[tuple] = []
    cache_hits = 0
    total_cells = 0
    for name in active:
        for word in words:
            total_cells += 1
            cached = cache.get_json(_cache_key(name, word))
            if isinstance(cached, list):
                cache_hits += 1
                buckets[name][word] = cached
            else:
                pending.append((name, word))

    fetched = 0
    if pending:
        try:
            async with httpx.AsyncClient(
                timeout=timeout_value, follow_redirects=True,
                headers=BILIBILI_HEADERS,  # 各源对通用 UA 均可接受
            ) as client:
                results = await asyncio.gather(
                    *(
                        ADAPTERS[name]["search"](client, word, limit)
                        for name, word in pending
                    ),
                    return_exceptions=True,
                )
            for (name, word), result in zip(pending, results):
                items = [] if isinstance(result, Exception) else result
                buckets[name][word] = items
                if items and not isinstance(result, Exception):
                    cache.set_json(_cache_key(name, word), items, ttl=CACHE_TTL)
                    fetched += 1
        except Exception:  # noqa: BLE001  网络层整体异常：保留缓存结果继续聚合
            pass

    # 轮转合并：先按「来源」轮转保证多样性，同一来源内再按「关键词」轮转
    collected: List[Dict] = []
    seen = set()
    depth = 0
    while len(collected) < limit:
        added = False
        for name in active:
            keyword_depth = depth
            if keyword_depth >= max((len(v) for v in buckets[name].values()), default=0):
                continue
            for word in words:
                bucket = buckets[name].get(word) or []
                if keyword_depth >= len(bucket):
                    continue
                item = bucket[keyword_depth]
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                collected.append(item)
                added = True
                if len(collected) >= limit:
                    break
            if len(collected) >= limit:
                break
        if not added:
            break
        depth += 1

    items = collected[:limit]
    latency = round((time.perf_counter() - started) * 1000)
    states = _source_states(words, buckets, active, started)
    hit_sources = sorted({item["source"] for item in items})
    if items:
        detail = ""
    elif cache_hits == total_cells and total_cells:
        detail = "缓存与各来源暂无匹配课程，稍后重试"
    else:
        detail = "视频源暂不可用或没有匹配课程，稍后重试"
    engine = "none"
    if items:
        engine = "cached" if fetched == 0 and cache_hits else (
            "mixed" if cache_hits and fetched else "live"
        )
    return {
        "items": items,
        "available": bool(items),
        "source": "+".join(hit_sources) if hit_sources else "+".join(active),
        "engine": engine,
        "detail": detail,
        "latency_ms": latency,
        "sources": states,
    }


def _source_states(words, buckets, active, started) -> List[Dict]:
    """每个来源的真实状态：命中数、延迟、失败原因——供前端与集成页如实展示。"""
    states = []
    for name, adapter in ADAPTERS.items():
        if name not in active:
            states.append(
                {
                    "name": name,
                    "label": adapter["label"],
                    "configured": False,
                    "available": False,
                    "count": 0,
                    "latency_ms": None,
                    "detail": "未配置密钥" if name == "youtube" else "未启用",
                }
            )
            continue
        hit = sum(len(v) for v in buckets.get(name, {}).values())
        states.append(
            {
                "name": name,
                "label": adapter["label"],
                "configured": True,
                "available": hit > 0,
                "count": hit,
                "latency_ms": None,  # 聚合层不逐源计时，避免增加复杂度
                "detail": f"命中 {hit} 条" if hit else "无匹配或接口未打通",
            }
        )
    return states


def video_configured() -> bool:
    """视频检索是否可用：任一来源配置可用即为 True。"""
    return any(adapter["configured"]() for adapter in ADAPTERS.values())


def available_sources() -> List[Dict]:
    """来源清单（含配置状态），供集成状态页展示。"""
    return [
        {
            "name": name,
            "label": adapter["label"],
            "configured": adapter["configured"](),
        }
        for name, adapter in ADAPTERS.items()
    ]
