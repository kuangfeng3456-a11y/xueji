"""容器健康检查脚本：请求本地 /api/health，3 秒超时，非 200 返回失败退出码。

slim 基础镜像没有 curl/wget，用标准库实现。供 Dockerfile HEALTHCHECK 使用。
"""

import os
import sys
import urllib.error
import urllib.request

url = "http://127.0.0.1:%s/api/health" % os.getenv("PORT", "8000")
try:
    with urllib.request.urlopen(url, timeout=3) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except (urllib.error.URLError, OSError):
    sys.exit(1)
