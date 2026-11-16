"""娱乐模块：全部走真实外部公开接口，失败时如实返回不可用，不伪造内容。"""

import time
from typing import Dict, List

import httpx

from ..cache import cache

TIMEOUT = 9.0
HEADERS = {"User-Agent": "Mozilla/5.0 (Xueji/1.0; adaptive learning coach)"}
CACHE_TTL = 300

KINDS: List[Dict] = [
    {"key": "hitokoto", "name": "一言", "desc": "中文短句与灵感", "source": "hitokoto.cn"},
    {"key": "poem", "name": "今日诗词", "desc": "一句古典诗词", "source": "jinrishici.com"},
    {"key": "quote", "name": "英文名言", "desc": "ZenQuotes 随机名言", "source": "zenquotes.io"},
    {"key": "joke", "name": "轻松一刻", "desc": "JokeAPI 安全笑话", "source": "jokeapi.dev"},
    {"key": "fact", "name": "冷知识", "desc": "随机趣味事实", "source": "uselessfacts.jsph.pl"},
    {"key": "wallpaper", "name": "每日壁纸", "desc": "Bing 每日图片", "source": "bing.com"},
]

KIND_MAP = {item["key"]: item for item in KINDS}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True, trust_env=False)


def _result(kind: str, title: str, content: str, author: str = "", image: str = "", link: str = "") -> Dict:
    source = KIND_MAP.get(kind, {})
    return {
        "kind": kind,
        "name": source.get("name", kind),
        "title": title,
        "content": content,
        "author": author,
        "image": image,
        "link": link,
        "source": source.get("source", ""),
        "engine": "network",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _error(kind: str, message: str) -> Dict:
    source = KIND_MAP.get(kind, {})
    return {
        "kind": kind,
        "name": source.get("name", kind),
        "status": "error",
        "error": message[:160],
        "source": source.get("source", ""),
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


async def _hitokoto(client) -> Dict:
    data = (await client.get("https://v1.hitokoto.cn/?encode=json")).json()
    return _result(
        "hitokoto",
        data.get("from") or "一言",
        data.get("hitokoto", ""),
        author=data.get("from_who") or "",
        link="https://hitokoto.cn",
    )


async def _poem(client) -> Dict:
    data = (await client.get("https://v1.jinrishici.com/all.json")).json()
    return _result(
        "poem",
        data.get("origin") or "今日诗词",
        data.get("content", ""),
        author=data.get("author") or "",
        link="https://jinrishici.com",
    )


async def _quote(client) -> Dict:
    data = (await client.get("https://zenquotes.io/api/random")).json()
    item = data[0] if isinstance(data, list) and data else {}
    return _result(
        "quote",
        "ZenQuotes",
        item.get("q", ""),
        author=item.get("a") or "",
        link="https://zenquotes.io",
    )


async def _joke(client) -> Dict:
    data = (await client.get("https://v2.jokeapi.dev/joke/Any?safe-mode&type=single")).json()
    return _result(
        "joke",
        data.get("category") or "轻松一刻",
        data.get("joke", ""),
        link="https://jokeapi.dev",
    )


async def _fact(client) -> Dict:
    data = (await client.get("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en")).json()
    return _result(
        "fact",
        "随机冷知识",
        data.get("text", ""),
        link=data.get("permalink", "https://uselessfacts.jsph.pl"),
    )


async def _wallpaper(client) -> Dict:
    data = (await client.get("https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1")).json()
    images = data.get("images") or []
    item = images[0] if images else {}
    url = item.get("url", "")
    if url.startswith("/"):
        url = "https://www.bing.com" + url
    return _result(
        "wallpaper",
        item.get("title") or "Bing 每日图片",
        item.get("copyright") or "",
        image=url,
        link=item.get("copyrightlink") or "https://www.bing.com",
    )


FETCHERS = {
    "hitokoto": _hitokoto,
    "poem": _poem,
    "quote": _quote,
    "joke": _joke,
    "fact": _fact,
    "wallpaper": _wallpaper,
}


async def fetch(kind: str, force: bool = False) -> Dict:
    if kind not in FETCHERS:
        return _error(kind, f"不支持的内容类型：{kind}")

    cache_key = f"fun:{kind}"
    if not force:
        cached = cache.get_json(cache_key)
        if cached:
            cached["cached"] = True
            return cached

    try:
        async with _client() as client:
            result = await FETCHERS[kind](client)
        if not result.get("content") and not result.get("image"):
            return _error(kind, "外部接口已连通，但未返回有效内容")
        cache.set_json(cache_key, result, ttl=CACHE_TTL)
        result["cached"] = False
        return result
    except Exception as exc:
        return _error(kind, f"{type(exc).__name__}: {exc}")


async def fetch_all() -> List[Dict]:
    results = []
    for kind in KIND_MAP:
        results.append(await fetch(kind))
    return results