"""学迹后端启动入口（发布版）。

同时托管 API 与已构建的前端静态资源，单端口对外提供服务。
发布环境下由平台注入 PORT，并需要绑定 0.0.0.0 才能被反向代理访问。
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


def _default_host() -> str:
    return os.getenv("HOST", "0.0.0.0")


def _default_port() -> int:
    raw = os.getenv("PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return 8000


def main() -> None:
    parser = argparse.ArgumentParser(description="启动学迹后端与已构建的前端页面")
    parser.add_argument("--host", default=_default_host())
    parser.add_argument("--port", type=int, default=_default_port())
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    # 前端产物放在 frontend/web（不叫 dist/build，避免发布打包时被当成构建产物忽略）。
    # 这里按本文件位置算绝对路径，不依赖启动时的工作目录。
    here = Path(__file__).resolve().parent
    os.environ.setdefault("FRONTEND_DIST", str(here.parent / "frontend" / "web"))
    os.environ.setdefault("UPLOAD_DIR", str(here / "uploads"))

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
