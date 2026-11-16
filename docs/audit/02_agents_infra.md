# 第二章 智能体与基础设施审计

## 1. 四智能体职责边界表

| Agent | 入口函数 | 输入 | 输出 | 依赖 service | LLM 用在哪一步 | 无 Key 兜底路径 |
|-------|---------|------|------|-------------|---------------|----------------|
| Planner | `planner_generate()` / `planner_replan()` | db Session, user_id, Goal, days | `{tasks[], summary}` | `services.planner.build_plan/replan`, `services.rules.days_left` | **仅润色 summary**：规则排程完成后，将任务摘要发给 LLM 生成≤70字今日重点 | `build_plan` 纯规则排程，summary 保留规则原文 |
| Diagnoser | `diagnose()` | question, user_answer, correct_answer, kp_name | `(category, label, suggestion, engine)` 四元组 | `services.rules.classify_mistake` | **语义归因**：LLM 输出 JSON `{category, suggestion}`，做枚举校验后采用 | `classify_mistake` 规则引擎（空答→time、相似→careless、步骤→method、其余→concept） |
| Coach | `coach_message()` | User, Goal, tasks[], streak, mistakes_7d, remain | 一段≤80字当日提醒字符串 | 无外部 service，内部 `_rule_message()` | **可选润色**：将规则生成的提醒发给 LLM 重写为更自然表达 | `_rule_message` 纯规则模板（逾期/全完成/冲刺期/常规四种分支） |
| Reporter | `reporter_generate()` | db Session, User, Goal, week_start | Report ORM 对象 | `services.reporting.generate_weekly_report` | **追加教练点评**：周报规则生成后，LLM 写≤120字点评拼接到 content 末尾 | `build_weekly_report` 纯规则统计+模板文案 |

### 多智能体协作判定

**结论：不是真正的多智能体协作，而是四个独立的"规则内核 + LLM 润色层"函数。**

- 四个 Agent 之间**无任何消息传递、任务委派或结果引用**。没有 orchestrator、没有 agent-to-agent 通信、没有共享工作记忆。
- 每个 Agent 的 LLM 调用都是**可选的后处理**：先由确定性规则产出完整结果，LLM 仅在 available 时做文本润色，失败不影响核心功能。
- `agents/skills.py` 中的 `SKILLS` 列表是**静态元数据注册表**（供 `/api/skills` 展示），不是运行时能力调度。
- `AgentRun` 表记录了每次调用的 agent_name/engine/latency，但这是**审计日志**，不是协作协议。
- 更准确的描述是：**单一规则引擎的四个功能模块，各带一个可选的 LLM 文本增强层**。

---

## 2. LLM 接入机制

### 2.1 客户端架构（`llm.py`）

`LLMClient` 是全局单例 `llm`，兼容 OpenAI Chat Completions 协议：

- **通道选择**：优先检查 `LLM_PRIMARY` 是否为 `maas/pangu` 且 `MAAS_BASE_URL/MAAS_API_KEY` 已配置，否则走 DeepSeek 通道（`LLM_BASE_URL/LLM_API_KEY`）。
- **HTTP 调用**：`httpx.AsyncClient(timeout=settings.LLM_TIMEOUT)`，默认超时 25 秒，`trust_env=False`。
- **请求格式**：标准 `messages: [{system}, {user}]`，temperature/max_tokens 可调。
- **JSON 解析**：`chat_json()` 用正则 `\{.*\}` 提取后 `json.loads`，失败返回 None。

### 2.2 熔断机制

```python
if self._consecutive_failures >= settings.LLM_FAILURE_THRESHOLD:  # 默认 3
    self._open_until = time.time() + settings.LLM_COOLDOWN_SECONDS  # 默认 60s
```

- 连续失败 ≥3 次 → 熔断 60 秒，期间 `available` 属性返回 False。
- 成功一次即重置 `_consecutive_failures`。
- 熔断粒度为进程级内存变量，**无跨进程/跨实例协调**。

### 2.3 Fallback 双网关

主通道异常时自动尝试 fallback：
- 配置项：`LLM_FALLBACK_BASE_URL` / `LLM_FALLBACK_API_KEY` / `LLM_FALLBACK_MODEL`
- 仅在 `chat()` 的 except 块中触发，**熔断期间不触发 fallback**（因为 `available` 已为 False，直接返回 None）。
- fallback 调用不计入主通道的 success/failures 计数，有独立 `fallback_calls` 计数器。

### 2.4 语义缓存

- 内存字典 `_cache`，key = SHA256(`model|system|normalized_user|temperature|max_tokens`)。
- TTL 600 秒，上限 500 条；超限时清理过期条目，仍超限则清空。
- 缓存命中跳过 HTTP 调用，直接返回。

### 2.5 Prompt 构造方式

所有 prompt 均为**代码内硬编码的 f-string**，无外部 prompt 模板文件。system prompt 明确约束输出格式（如"只输出 JSON""不超过 N 字""不得编造"），user prompt 拼接业务数据。

### 2.6 失败降级路径总结

```
LLM 调用 → 缓存命中? → 是 → 返回缓存
         → 否 → HTTP 请求 → 成功 → 缓存+返回
                            → 失败 → fallback 配置? → 是 → fallback HTTP → 成功/失败
                                                      → 否 → 返回 None
                                                         ↓
                                              Agent 收到 None → 使用规则引擎结果
```

---

## 3. 数据模型全景

实际 ORM 定义了 **33 张表**（非 README 宣称的 37 张）。按业务域分组：

### 3.1 核心学习域

| 表名 | 主键 | 关键外键 | 索引 | 备注 |
|------|------|---------|------|------|
| users | id | — | username(unique+index) | 无 updated_at、无软删除 |
| goals | id | user_id→users | user_id | 无 updated_at |
| knowledge_points | id | goal_id→goals, parent_id→self | goal_id | 自引用树结构 |
| mastery | id | user_id→users, kp_id→knowledge_points | user_id, kp_id; UQ(user_id,kp_id) | 当前掌握度快照 |
| mastery_history | id | user_id→users, kp_id→knowledge_points | user_id, kp_id, day; UQ(user_id,kp_id,day) | 按日掌握度时序 |
| tasks | id | user_id→users, goal_id→goals, kp_id→knowledge_points | user_id, goal_id, day | status 枚举无 DB 约束 |
| mistakes | id | user_id→users, goal_id→goals, kp_id→knowledge_points | user_id, goal_id | image_url 通过 ALTER TABLE 补加 |
| reports | id | user_id→users, goal_id→goals | user_id, goal_id; UQ(user_id,goal_id,week_start) | 周报 |
| materials | id | user_id→users, goal_id→goals | user_id, goal_id | 资料文本存储 |
| replan_logs | id | user_id→users, goal_id→goals | user_id, goal_id | 重排审计 |
| learning_events | id | user_id→users, goal_id→goals, kp_id→knowledge_points | user_id, goal_id, event_type, kp_id, occurred_at | 统一事件流 |

### 3.2 社交与班级

| 表名 | 主键 | 关键外键 | 索引 | 备注 |
|------|------|---------|------|------|
| classes | id | owner_id→users | invite_code(unique+index), owner_id | 班级 |
| class_members | id | class_id→classes, user_id→users | class_id, user_id; UQ(class_id,user_id) | 成员角色 |
| buddies | id | user_id→users, buddy_id→users | user_id, buddy_id; UQ(user_id,buddy_id) | 学习搭子 |

### 3.3 专注与行为

| 表名 | 主键 | 关键外键 | 索引 | 备注 |
|------|------|---------|------|------|
| focus_sessions | id | user_id→users, goal_id→goals, task_id→tasks | user_id, goal_id | 番茄钟会话 |
| violations | id | user_id→users, goal_id→goals | user_id, goal_id, day | 违规记录 |

### 3.4 知识图谱与诊断

| 表名 | 主键 | 关键外键 | 索引 | 备注 |
|------|------|---------|------|------|
| knowledge_dependencies | id | goal_id→goals, from_kp_id/to_kp_id→knowledge_points | goal_id, from_kp_id, to_kp_id; UQ(goal_id,from_kp_id,to_kp_id) | 先修关系 |
| knowledge_edges | id | goal_id→goals, from_kp_id/to_kp_id→knowledge_points | goal_id, from_kp_id, to_kp_id | 显式知识关系（prerequisite/confusable/related） |
| knowledge_gaps | id | user_id→users, goal_id→goals, kp_id→knowledge_points | user_id, goal_id, kp_id | 知识漏洞候选 |
| risk_predictions | id | user_id→users, goal_id→goals, kp_id→knowledge_points | user_id, goal_id, kp_id; UQ(user_id,goal_id,kp_id) | 风险预警 |

### 3.5 AI 审计与实验

| 表名 | 主键 | 关键外键 | 索引 | 备注 |
|------|------|---------|------|------|
| agent_runs | id | user_id→users, goal_id→goals | run_id, user_id, goal_id | 智能体运行审计 |
| eval_runs | id | user_id→users | run_id | AI 可靠性评测 |
| learning_experiments | id | user_id→users, goal_id→goals | user_id, goal_id | 策略实验 |
| experiment_metrics | id | experiment_id→learning_experiments, user_id→users, goal_id→goals | experiment_id, user_id, goal_id | 实验指标 |
| probe_items | id | user_id→users, goal_id→goals, kp_id→knowledge_points | user_id, goal_id | 探测题 |
| thought_traces | id | user_id→users, goal_id→goals, mistake_id→mistakes | user_id, goal_id, mistake_id; UQ(mistake_id) | 思维链追溯 |
| panel_reviews | id | user_id→users, goal_id→goals | user_id, goal_id | 多角色评审 |
| evidence_chain | id | user_id→users, goal_id→goals | user_id, goal_id | 决策证据链 |

### 3.6 其他

| 表名 | 主键 | 关键外键 | 索引 | 备注 |
|------|------|---------|------|------|
| skill_packages | id | — | slug(unique+index) | 技能包市场 |
| psychology_assessments | id | user_id→users | user_id | 心理量表 |
| freshness_reports | id | user_id→users, goal_id→goals, material_id→materials | user_id, goal_id, material_id; UQ(material_id) | 资料时效 |
| document_chunks | id | user_id→users, goal_id→goals, material_id→materials | user_id, goal_id, material_id | RAG 切块 |
| consent_records | id | user_id→users | user_id | 家长授权 |

### 3.7 缺失与问题

- **表数量不符**：实际 33 张，README 宣称 37 张。
- **无软删除**：所有表均无 `deleted_at` / `is_deleted` 字段，账号删除为物理删除。
- **时间戳不一致**：全部使用 `default=datetime.utcnow`（UTC），但部分业务逻辑用 `date.today()`（本地时间），存在时区混淆风险。
- **缺少复合索引**：`tasks` 表高频查询 `(user_id, goal_id, day)` 无复合索引；`mistakes` 表 `(user_id, goal_id, created_at)` 同理。
- **status 字段无 CHECK 约束**：tasks.status、focus_sessions.status 等枚举值仅靠应用层校验。
- **knowledge_edges.created_at 重复定义**：该字段在模型中被声明了两次（第 499-500 行），SQLAlchemy 会使用后一个定义，但属于代码瑕疵。

---

## 4. 缓存与限流

### 4.1 Redis / 内存双后端切换（`cache.py`）

```python
class Cache:
    def __init__(self):
        self._fallback = MemoryCache()
        self._redis = None
        if settings.REDIS_URL:
            try:
                client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, ...)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None
```

- **启动时一次性探测**：`REDIS_URL` 非空时尝试连接+ping，失败则 `_redis=None`。
- **运行时不自动降级**：如果 Redis 在运行中断连，`get_json/set_json/delete/incr` 的 Redis 操作会抛异常被 except 捕获，静默回退到内存缓存，但不会更新 `_redis` 引用。
- **双写策略**：`set_json` 同时写 Redis 和内存；`get_json` 先查 Redis，miss 再查内存。这意味着内存缓存始终有数据副本。
- **MemoryCache** 使用 `threading.Lock` 保证线程安全，支持 TTL 过期和原子 incr。

### 4.2 缓存键设计

| 前缀 | 用途 | TTL |
|------|------|-----|
| `ai:insights:{user_id}:{goal_id}:{date}:...` | 学情洞察 AI 报告 | 1800s |
| `ai:forecast:{goal_id}:...` | 冲刺策略 AI 建议 | 1800s |
| `ai:card:{kp_id}` | 闪卡 AI 释义 | 86400s |
| `ratelimit:diagnose:{user_id}` | 错题诊断限流计数 | 60s |
| `integration:ping:{uuid}` | 集成测试临时键 | 10s |

### 4.3 限流

项目中**仅有一处限流**：错题诊断接口 `POST /api/learning/{goal_id}/diagnose`。

```python
count = cache.incr(f"ratelimit:diagnose:{user.id}", ttl=60)
if count > 30:
    raise HTTPException(status_code=429, detail="错题诊断过于频繁，请稍后再试")
```

- 算法：固定窗口计数器，60 秒窗口内最多 30 次。
- 其他所有 API 端点**无限流**。

---

## 5. 数据库降级链路

### 5.1 URL 拼接（`config.py`）

```python
def _build_database_url():
    configured = os.getenv("DATABASE_URL", "").strip()
    host = _first_env("RDS_INTRANET_HOST", "RDS_HOST", "HUAWEI_RDS_HOST")
    if host and (not configured or configured.startswith("sqlite")):
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    if configured:
        return configured
    return f"sqlite:///{(BASE_DIR / 'xueji.db').as_posix()}"
```

优先级：`RDS_*_HOST` 环境变量 > `DATABASE_URL` > 本地 SQLite。

### 5.2 连接探活与降级（`database.py`）

```python
def resolve_database(primary_url, ...):
    backend = "rds" if "mysql" in primary_url else "sqlite"
    active_engine = engine_factory(primary_url)
    if backend != "rds":
        return DatabaseRuntime(primary_url, backend, False, "", active_engine)
    error = probe(active_engine)  # SELECT 1
    if not error:
        return DatabaseRuntime(primary_url, backend, False, "", active_engine)
    active_engine.dispose()
    fallback_url = f"sqlite:///{local_sqlite.as_posix()}"
    return DatabaseRuntime(fallback_url, "sqlite-fallback", True, error, fallback_engine)
```

- 仅在**启动时**执行一次探活（`SELECT 1`），运行时不再重新检测。
- 降级后 `ACTIVE_DATABASE_BACKEND = "sqlite-fallback"`，`DATABASE_FALLBACK = True`。
- 这三个变量通过 `/api/health` 和 `/api/integrations` 暴露给前端。

### 5.3 注意事项

- 降级是**单向的**：启动时 RDS 不可达 → SQLite；运行期间 RDS 恢复不会自动切回。
- SQLite 模式下 `pool_pre_ping`、连接池参数不适用（使用了 `check_same_thread=False`）。
- `.env.cloud` 优先于 `.env` 加载，便于云参数覆盖本地配置。

---

## 6. 鉴权与安全

### 6.1 JWT 签发与校验

- **算法**：HS256，使用 `python-jose` 库。
- **Payload**：`{sub: user_id, username, exp}`，过期时间默认 10080 分钟（7 天）。
- **签发**：登录/注册成功后立即签发，无 refresh token 机制。
- **校验**：`HTTPBearer` 从 Authorization header 提取 token → `jwt.decode` → 查库获取 User。

### 6.2 密码哈希

```python
hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
```

- PBKDF2-SHA256，120000 轮迭代，16 字节随机 salt。
- 存储格式：`pbkdf2_sha256$120000${salt_b64}${digest_b64}`。
- 验证使用 `hmac.compare_digest` 防时序攻击。

### 6.3 权限依赖

- `get_current_user`：从 Bearer token 解析用户，无效/过期返回 401。
- `get_user_goal(goal_id, user, db)`：校验 goal.user_id == current_user.id，防止越权访问。
- **无 RBAC/角色系统**：所有已登录用户权限相同，无管理员/教师/学生区分。

### 6.4 CORS 配置

```python
allow_origins=settings.CORS_ORIGINS  # 默认 localhost:5173, :8080
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

### 6.5 上传限制

`MAX_UPLOAD_BYTES = 5 * 1024 * 1024`（5MB），但此常量**未在代码中被引用**进行实际校验（需确认上传接口是否手动检查）。

### 6.6 数据导出与账号删除

- **导出**：`GET /api/auth/me/export` 返回 JSON，包含用户、目标、知识点、掌握度、任务、错题、资料、周报、重排日志。
- **删除**：`DELETE /api/auth/me` 物理删除用户及关联数据（MasteryHistory → Mastery → Task → Mistake → Report → Material → ReplanLog → KnowledgePoint → User）。

### 6.7 安全隐患

| 风险 | 详情 |
|------|------|
| **默认 SECRET_KEY** | `"xueji-dev-secret-please-change"` 硬编码为默认值，部署时若未设置环境变量，所有 JWT 可被伪造 |
| **Token 有效期过长** | 7 天无 refresh 机制，泄露后窗口期长 |
| **无全局限流** | 仅错题诊断有限流，登录/注册/计划生成等敏感接口无防护，易被暴力破解或滥用 |
| **SQL 注入面** | `ensure_schema()` 中使用 f-string 拼接 `ALTER TABLE {table} ADD COLUMN {name} {ddl}`，虽然 table/name 来自硬编码字典，但模式不安全 |
| **日志可能含敏感信息** | access_log 中间件记录完整 URL path，若 path 中含 token 或用户数据会被写入日志文件 |
| **datetime.utcnow 已弃用** | Python 3.12+ 中 `datetime.utcnow()` 被标记为 deprecated，应使用 `datetime.now(timezone.utc)` |
| **上传大小限制未生效** | `MAX_UPLOAD_BYTES` 定义了但未在上传接口中实际校验（需进一步确认 focus/upload 接口） |
| **账号删除不完整** | 未删除 FocusSession、Violation、Buddy、ClassMember、ConsentRecord、PsychologyAssessment、LearningEvent 等关联表数据 |

---

## 7. 华为云接入真实程度

### 7.1 `huawei_cloud.py` — 真实 SDK 调用

该文件**确实调用了华为云 SDK**：
- `from huaweicloudsdkrds.v3 import RdsClient` — RDS 实例列表查询
- `from huaweicloudsdkdcs.v2 import DcsClient` — DCS 实例列表查询
- 使用 `BasicCredentials(ak, sk, project)` 认证
- 查询失败如实返回错误信息，不伪造状态

但注意：**SDK 包不在 requirements.txt 中**。`huaweicloudsdkrds`、`huaweicloudsdkdcs`、`huaweicloudsdkcore` 均未列入依赖清单，意味着在未手动安装的环境中 `cloud_instances()` 会在 import 阶段失败，被 except 捕获后返回"云客户端初始化失败"。

### 7.2 `provision_cloud.py` — 文件存在且真实

- 路径：`D:\90\backend\scripts\provision_cloud.py`，301 行。
- 支持 `--dry-run` / `--apply` / `--rds-only` / `--redis-only` 模式。
- 真实调用华为云 SDK 创建 RDS MySQL 和 DCS Redis 实例。
- 自动生成密码并写入 `.env.cloud`。

### 7.3 `migrate_to_rds.py` — 文件存在

- 路径：`D:\90\backend\scripts\migrate_to_rds.py`，3.9 KB。
- 用于将本地 SQLite 数据迁移到 RDS MySQL。

### 7.4 接入真实度总结

| 组件 | 代码真实性 | 运行时可用性 | 备注 |
|------|-----------|-------------|------|
| RDS MySQL 连接 | ✅ 真实 pymysql 驱动 | ✅ 有 HOST 即可连 | 降级链路完整 |
| DCS Redis 连接 | ✅ 真实 redis-py 客户端 | ✅ 有 URL 即可连 | 启动时 ping 探活 |
| 华为云 SDK 查询 | ✅ 真实 SDK 调用 | ⚠️ SDK 未入 requirements.txt | 需手动 pip install |
| provision_cloud.py | ✅ 文件存在，301行 | ⚠️ 同上 SDK 依赖问题 | 功能完整 |
| migrate_to_rds.py | ✅ 文件存在 | 未深入审计 | — |
| OBS 对象存储 | ⚠️ 仅有配置项 | ❌ 无实际调用代码 | `STORAGE_BACKEND` 默认 local |
| OCR / SIS | ⚠️ 仅有配置项 | ❌ 无服务端调用代码 | 降级到浏览器原生能力 |
