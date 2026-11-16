# syntax=docker/dockerfile:1

# ---------------- 前端构建阶段 ----------------
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------- 后端运行阶段 ----------------
FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    TZ=Asia/Shanghai \
    FRONTEND_DIST=/app/web/dist
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/run.py ./
COPY backend/scripts/healthcheck.py /opt/health/hc.py
COPY --from=web /web/dist ./web/dist

# ---- 安全加固：非 root 运行（uid 固定 10001，便于 CCE securityContext 校验）----
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --no-create-home appuser \
    && mkdir -p /app/data /app/uploads /app/logs \
    && chown -R appuser:appuser /app/data /app/uploads /app/logs

EXPOSE 8000
# 探针路径与 app/main.py 的 /api/health 一致
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "/opt/health/hc.py"]

# 运行时数据必须由卷挂载，不写入镜像层
VOLUME ["/app/data", "/app/uploads", "/app/logs"]

USER 10001:10001
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]