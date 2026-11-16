"""媒体代理：B 站图床等外链封面按 Referer 防盗链，页面直接引用会被判 403。

这里在服务端取回图片并以流的形式转发，前端只引用本站地址。
严格白名单域名，避免被当成 SSRF 跳板。
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(tags=["媒体代理"])

# 仅允许 B 站图床与头像域名
ALLOWED_HOSTS = {
    "i0.hdslb.com",
    "i1.hdslb.com",
    "i2.hdslb.com",
    "archive.biliimg.com",
}

# 伪装成从 B 站站内发起，绕过图床防盗链
UPSTREAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}


@router.get("/media/image")
def proxy_image(url: str = Query(..., description="原始图片地址")) -> Response:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="仅支持 http/https 地址")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="该域名不在代理白名单内")

    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            upstream = client.get(url, headers=UPSTREAM_HEADERS)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"图片源不可达：{exc}") from exc

    if upstream.status_code != 200:
        raise HTTPException(status_code=502, detail=f"图片源返回 {upstream.status_code}")

    content_type = (upstream.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        # 防盗链命中时图床会返回 HTML 错误页，直接拒绝，避免把 HTML 当图片吐给前端
        raise HTTPException(status_code=415, detail="图片源未返回图片内容")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Proxy-Source": "bilibili",
        },
    )
