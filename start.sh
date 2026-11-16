#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PORT="${1:-8000}"

if [ ! -f frontend/dist/index.html ]; then
  echo "[1/3] 构建前端..."
  (cd frontend && npm install --no-audit --no-fund && npm run build)
else
  echo "[1/3] 前端已构建，跳过"
fi

echo "[2/3] 安装后端依赖..."
python -m pip install -r backend/requirements.txt -q

echo "[3/3] 初始化演示数据并启动..."
cd backend
python -m app.seed
python run.py --port "$PORT"