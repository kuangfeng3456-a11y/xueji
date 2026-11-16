# 🚀 学迹项目快速操作手册

## 启动状态

✅ **后端服务已启动**

```
地址: http://127.0.0.1:8000
状态: 运行中
进程: uvicorn (Python FastAPI)
```

---

## 🌐 访问地址

| 应用 | 地址 | 说明 |
|------|------|------|
| **前端主页** | http://127.0.0.1:8000 | 学迹 AI 学习教练 |
| **API 文档** | http://127.0.0.1:8000/docs | Swagger UI（交互式） |
| **API 文档** | http://127.0.0.1:8000/redoc | ReDoc（只读） |
| **健康检查** | http://127.0.0.1:8000/api/health | 服务状态 |

---

## 🔐 演示账号

| 字段 | 值 |
|------|-----|
| 用户名 | `demo` |
| 密码 | 由 `python -m app.seed` 生成并打印；仓库中不保存固定口令 |

> 需要固定口令时，先设置环境变量 `SEED_DEMO_PASSWORD`，再执行 `python -m app.seed --reset`。
> 想让登录页显示演示账号提示，额外设置 `DEMO_HINT="demo / <密码>"`；商用部署两个变量都留空。

---

## ⚡ 三个关键操作

### 1️⃣ 配置外部题库（一键完成）

```bash
cd backend
python setup_external_qbank.py --configure
```

**交互步骤**：
1. 输入题库 API 地址（如 `https://api.example.com/questions`）
2. 输入 API 密钥（可选）
3. 输入超时时间（默认 8 秒）

配置自动保存到 `.env` 文件。

---

### 2️⃣ 测试题库连接

```bash
# 使用配置文件中的设置
python setup_external_qbank.py --check

# 或指定 URL 和 Key 进行测试
python setup_external_qbank.py --test \
  https://your-api.com/questions \
  your_api_key
```

**预期输出**：
```
✓ 连接成功！
  HTTP 状态码：200
  返回题数：5
  响应时间：234.5ms
```

---

### 3️⃣ 使用系统

1. 打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)
2. 使用 `python -m app.seed` 输出的账号登录（默认用户名 demo）
3. 创建学习目标或进入已有目标
4. **选择知识点** → **点击出题**
5. 题目将从外部题库获取（或自动降级）

---

## 📡 API 快速参考

### 登录

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"<seed 输出的密码>"}'
```

响应包含 `access_token`，用于后续请求的 Authorization 头。

### 获取目标列表

```bash
curl http://127.0.0.1:8000/api/goals \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 出题（核心操作）

```bash
curl -X POST http://127.0.0.1:8000/api/goals/{goal_id}/quiz/generate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "kp_id": 1,           # 知识点 ID
    "count": 5            # 需要的题数
  }'
```

### 获取题库信息

```bash
curl http://127.0.0.1:8000/api/goals/{goal_id}/question-banks/info \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 完整 API 文档

访问 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)，可在浏览器中交互式调用所有 API。

---

## 🔧 系统管理

### 查看运行日志

```bash
# 实时日志（需另开终端）
cd backend
tail -f logs/app.log

# 或从 Kiro 进程输出查看
# （按照 Kiro 的 get_process_output 工具）
```

### 重启服务

```bash
# 停止（在后端服务的终端按 Ctrl+C）
# 然后重启
cd backend
python run.py --port 8000
```

### 改变服务端口

```bash
python run.py --port 9000  # 使用 9000 端口
```

### 查看配置信息

```bash
python -c "
from app.config import settings
print('=== 当前配置 ===')
print(f'数据库：{settings.DATABASE_URL.split(\"@\")[0]}')
print(f'缓存：{settings.REDIS_URL or \"内存缓存\"}')
print(f'LLM 模型：{settings.LLM_MODEL}')
print(f'外部题库：{settings.QUESTION_BANK_API_URL or \"未配置\"}')
"
```

---

## 🐛 常见问题

### Q: 访问首页显示乱码？

**A**: 刷新页面即可。这是编码初始化的问题，已自动处理。

### Q: 数据库无法连接？

**A**: 系统已自动降级到本地 SQLite。这是正常的。

要使用云 MySQL，需要：
1. MySQL 服务已启动
2. 在 `.env` 中配置 `DATABASE_URL`
3. 重启后端

### Q: Redis 连接失败？

**A**: 系统已自动使用内存缓存。这是正常的。

要启用 Redis：
1. Redis 服务已启动
2. 在 `.env` 中配置 `REDIS_URL`
3. 重启后端

### Q: 外部题库出题速度慢？

**A**: 这是正常的，网络延迟会增加响应时间。可以：
1. 检查外部题库 API 的响应时间
2. 启用 Redis 缓存以加速
3. 调整超时时间

### Q: 出题返回的是本地题库而不是外部题库？

**A**: 检查以下几点：
1. 是否配置了外部题库（运行 `setup_external_qbank.py --check`）
2. 后端是否已重启（配置后必须重启）
3. 外部题库 API 是否真的可达（运行测试）
4. 返回的题目知识点是否与请求一致

### Q: 如何切换回本地题库？

**A**: 修改 `.env` 文件注释掉外部题库设置，然后重启：

```env
# QUESTION_BANK_API_URL=...
PRIMARY_QUESTION_BANK=local
```

---

## 📊 系统架构简图

```
┌─────────────────────────────────────┐
│         浏览器前端 (Vue 3)           │
│   http://127.0.0.1:8000            │
└──────────────────┬──────────────────┘
                   │ HTTP/REST API
                   ↓
┌─────────────────────────────────────┐
│      后端服务 (FastAPI)              │
│   http://127.0.0.1:8000             │
│                                      │
│  ┌───────────────────────────────┐ │
│  │  出题逻辑 (quiz.py)           │ │
│  │  优先级:                      │ │
│  │  1. 外部题库 ⭐              │ │
│  │  2. 内置题库                 │ │
│  │  3. LLM 补题                 │ │
│  │  4. 规则兜底                 │ │
│  └───────────────────────────────┘ │
│                  ↓                   │
│  ┌───────────────────────────────┐ │
│  │  数据库 (SQLite/MySQL)        │ │
│  │  缓存 (Redis/内存)            │ │
│  └───────────────────────────────┘ │
└──────────────────┬──────────────────┘
                   │
        ┌──────────┴──────────┐
        ↓                     ↓
┌───────────────┐    ┌──────────────────┐
│ 外部题库 API  │    │ LLM (DeepSeek)   │
│ (用户配置)    │    │ (可选)           │
└───────────────┘    └──────────────────┘
```

---

## 🎯 工作流示例

### 场景：登录 → 创建目标 → 出题

#### 步骤 1: 登录

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"<seed 输出的密码>"}'

# 返回：{"access_token":"...","token_type":"bearer"}
```

#### 步骤 2: 获取目标

```bash
curl http://127.0.0.1:8000/api/goals \
  -H "Authorization: Bearer ACCESS_TOKEN"

# 返回目标列表，记下 goal_id（如 1）
```

#### 步骤 3: 获取知识点

```bash
curl http://127.0.0.1:8000/api/goals/1/knowledge-points \
  -H "Authorization: Bearer ACCESS_TOKEN"

# 返回知识点列表，记下 kp_id（如 5）
```

#### 步骤 4: 出题

```bash
curl -X POST http://127.0.0.1:8000/api/goals/1/quiz/generate \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"kp_id":5,"count":3}'

# 返回 3 道题，来源自外部题库（或自动降级）
```

---

## 📈 监控与统计

### 查看 API 调用统计

```bash
# 从日志中统计出题次数
grep "quiz/generate" backend/logs/app.log | wc -l

# 查看平均响应时间
grep "quiz/generate" backend/logs/app.log | \
  awk '{print $NF}' | \
  sort -n | \
  awk '{sum+=$1; count++} END {print "平均响应时间: " sum/count "ms"}'
```

### 监控题库来源分布

```bash
# 统计外部题库命中率
grep "source.*external" backend/logs/app.log | wc -l
grep "source.*local" backend/logs/app.log | wc -l
grep "source.*llm" backend/logs/app.log | wc -l
```

---

## 🚀 生产部署

### Docker 启动（可选）

```bash
# 构建镜像
docker build -t xueji:latest .

# 启动容器
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL=mysql+pymysql://user:pass@mysql:3306/xueji \
  -e REDIS_URL=redis://redis:6379/0 \
  -e QUESTION_BANK_API_URL=https://your-api.com/questions \
  --name xueji \
  xueji:latest
```

### 环境变量清单

必填：
- `QUESTION_BANK_API_URL` - 外部题库地址

可选：
- `DATABASE_URL` - 数据库连接（默认 SQLite）
- `REDIS_URL` - Redis 缓存（默认内存缓存）
- `LLM_BASE_URL` - LLM 服务地址
- `LLM_API_KEY` - LLM 密钥

---

## 📞 获得帮助

1. **查看日志**：`tail -f backend/logs/app.log`
2. **API 文档**：http://127.0.0.1:8000/docs
3. **健康检查**：curl http://127.0.0.1:8000/api/health
4. **配置检查**：`python backend/setup_external_qbank.py --check`

---

**现在可以开始使用学迹系统了！🎉**
