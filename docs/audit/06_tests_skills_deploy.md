# 06 测试体系、Skill 包体系与部署运维审计

## 1. 测试体系

### 1.1 测试文件清单

| 文件名 | 测试对象 | `def test_` 数 | 测试层面 |
|---|---|---|---|
| conftest.py | fixture / 隔离 | 0（辅助） | — |
| test_rules.py | 纯规则函数 | 16 | 单元 |
| test_llm.py | LLM 客户端 | 9 | 单元 |
| test_database.py | 数据库连接/降级 | 11 | 单元 |
| test_agents_cache.py | 智能体缓存 | 22 | 单元 |
| test_main.py | 应用启动/中间件 | 17 | 集成 |
| test_api_core.py | 认证/目标/资料 CRUD | 14 | API 集成 |
| test_api_dashboard.py | 首页仪表盘 | 8 | API 集成 |
| test_api_learning.py | 学习/答题/掌握度 | 24 | API 集成 |
| test_api_coach.py | 教练消息 | 23 | API 集成 |
| test_api_social.py | 班级/学伴/搜索 | 36 | API 集成 |
| test_api_skill_market.py | Skill 包市场 | 18 | API 集成 |
| test_api_ai_lab.py | AI 实验室全功能 | 28 | API 集成 |
| test_api_innovation.py | 创新赛特色接口 | 18 | API 集成 |
| test_planner.py | 排程服务 | 17 | Service |
| test_reporting.py | 周报生成 | 8 | Service |
| test_materials.py | 资料导入解析 | 16 | Service |
| test_auto_schedule.py | 自动排课 | 12 | Service |
| test_focus.py | 专注计时 | 20 | Service |
| test_forecast.py | 成绩预测 | 23 | Service |
| test_insights.py | 学习洞察 | 20 | Service |
| test_flashcards.py | 闪卡系统 | 21 | Service |
| test_quiz.py | 测验出题 | 35 | Service |
| test_knowledge_map.py | 知识图谱/漏洞 | 14 | Service |
| test_readiness.py | 准备度/风险 | 14 | Service |
| test_mastery_rhythm.py | 掌握度节奏 | 13 | Service |
| test_experiments.py | 策略实验 | 9 | Service |
| test_simulation_plan.py | 策略模拟 | 11 | Service |
| test_twin.py | 数字孪生 | 2 | Service |
| test_cognitive_load.py | 认知负荷 | 17 | Service |
| test_evidence.py | 证据链 | 10 | Service |
| test_freshness.py | 时效雷达 | 18 | Service |
| test_panel.py | AI 评审团 | 12 | Service |
| test_probes.py | AI 探针 | 33 | Service |
| test_thought_trace.py | 思维回放 | 10 | Service |
| test_ai_content.py | AI 内容生成 | 17 | Service |
| test_fatigue_relief.py | 疲劳缓解 | 7 | Service |
| test_seed.py | 演示数据种子 | 3 | 集成 |
| test_integrations.py | 外部服务接入中心 | 21 | 集成 |
| **合计** | **38 个测试文件** | **627** | — |

### 1.2 驱动方式与隔离机制

**ASGI 驱动**：因 Starlette 0.27 与 httpx 0.28 不兼容，项目未使用 `starlette.testclient.TestClient`，而是在 `conftest.py` 中自定义 `api` fixture，通过 `httpx.ASGITransport(app=app)` + `asyncio.run()` 同步调用异步 ASGI 应用。该方案可行但每次请求都新建 `AsyncClient`，有一定性能开销。

**数据库隔离**：`fresh_database` autouse fixture 在每个用例前后执行 `drop_all` + `create_all`，配合内存 SQLite（`sqlite:///.../.pytest-tmp/test.db`），保证用例间完全隔离。同时清空内存缓存 `cache._fallback._data`。

**云服务隔离**：`forbid_real_cloud_connections` autouse fixture 在模块导入阶段就将 RDS_HOST、REDIS_HOST 等 12 个环境变量置空，并在每个用例中断言 `DATABASE_URL` 必须以 `sqlite` 开头、`ACTIVE_DATABASE_BACKEND == "sqlite"`、Redis 为 None。这是非常严格的防御性设计。

**LLM 隔离**：`disable_real_llm` autouse fixture 断言 `LLM_BASE_URL` 和 `LLM_API_KEY` 为空，并通过 monkeypatch 将 llm 实例的 base_url/api_key 置空。`test_llm.py` 还额外定义了 `_ForbiddenClient`，若测试中意外创建真实 HTTP 客户端则立即 AssertionError。

### 1.3 真实覆盖率 vs README 宣称

| 指标 | README 宣称 | coverage_report.txt 实际 | 差异 |
|---|---|---|---|
| 通过用例数 | 636 passed + 1 skipped | **155 passed + 1 skipped** | **虚报 4.1 倍** |
| 行覆盖率 | 约 98% | **97.90%**（2562/2617） | 基本一致 |
| 门槛 | — | 80%，已通过 | — |

**关键发现**：README 第 293 行写 `python -m pytest -q # 636 passed + 1 skipped`，但 `coverage_report.txt` 明确记录 `155 passed, 1 skipped, 1 warning in 79.16s`。代码中 `def test_` 定义共 627 个，加上参数化展开（约 7 组 parametrize，估计增加 ~20 个用例），理论上限约 650 左右，与实际运行 155 差距巨大。**最可能的解释是 README 中的 636 来自某次包含更多测试文件或不同 pytest 配置的运行结果，而当前提交的 coverage_report.txt 是另一次不完整运行的产物；或者 636 是预期值而非实测值。** 无论哪种情况，README 数字与仓库内可验证的报告不一致，属于严重可信度问题。

覆盖率 97.90% 本身可信，但需注意以下未被覆盖的文件不在统计范围内：`app/services/simulation.py`、`app/services/readiness.py`、`app/services/knowledge_map.py`、`app/services/probes.py`、`app/services/thought_trace.py`、`app/services/panel.py`、`app/services/freshness.py`、`app/services/cognitive_load.py`、`app/services/evidence.py`、`app/services/experiments.py`、`app/api/ai_lab.py`、`app/api/cockpit.py`、`app/api/risks.py`、`app/api/simulation.py`、`app/api/experiments.py`、`app/api/evidence.py`、`app/api/knowledge.py` 等——这些文件要么未被 trace 收集到（可能是异步代码路径未被触发），要么根本不在 `app/` 目录下被扫描。**覆盖率报告只列出了 29 个文件，而 app 目录下实际有更多 .py 文件未被列入统计。**

### 1.4 自研覆盖率工具可信度评价

`run_coverage.py` 基于标准库 `trace` 模块实现，有以下局限：

| 维度 | 评价 |
|---|---|
| 同步代码 | ✅ 可靠，`sys.settrace` 能捕获所有同步行事件 |
| 异步代码 | ⚠️ 部分可靠。虽然设置了 `threading.settrace`，但 asyncio 协程在事件循环内的行事件取决于 tracer 是否在正确的线程上激活。FastAPI 的 async 路由在 uvicorn 的事件循环线程中执行，而 pytest 通过 `asyncio.run()` 在新线程中运行协程，tracer 可能丢失部分异步路径 |
| 未导入模块 | ❌ 无法统计。`trace` 只能记录被执行到的行，未被 import 的模块不会出现在报告中，这与 coverage.py 的 `--source` 模式不同 |
| 分支覆盖 | ❌ 不支持，仅行覆盖 |
| 子进程/多进程 | ❌ 不支持 |
| 性能开销 | 中等，trace 回调对每行都有 Python 层开销 |

**结论**：97.90% 的数字对已覆盖的 29 个文件可信，但该工具遗漏了未被导入或纯异步执行的模块，实际全量覆盖率可能低于报告值。建议补充使用标准 `coverage.py` 进行交叉验证。

### 1.5 测试质量具体问题

| 问题类型 | 文件 / 用例 | 说明 |
|---|---|---|
| 用例极少 | test_twin.py（2 个） | 数字孪生是核心创新点，但只有聚合测试和空数据测试，缺少边界、异常和部分数据场景 |
| 用例极少 | test_seed.py（3 个） | 种子数据是演示基础，但只测了正常生成、班级创建和幂等性，未验证数据内容的正确性细节 |
| 用例极少 | test_fatigue_relief.py（7 个） | 疲劳缓解是 2.0 新功能，测试覆盖面偏窄 |
| 断言偏弱 | test_api_dashboard.py::test_dashboard_with_goal_and_plan | 只检查列表长度和固定字符串，未验证任务内容、优先级排序等核心业务逻辑 |
| 断言偏弱 | test_reporting.py::test_weekly_report_without_baseline | 用 `or` 连接两个互斥断言（`"保持当前节奏" in ... or "优先补" in ...`），永远通过 |
| mock 合理 | test_llm.py | 使用 `_ForbiddenClient` 防止真实调用，mock 粒度恰当，未过度 mock |
| mock 合理 | test_reporting.py | `_FakeLLM` 只替换 llm 实例，保留了完整的报表生成逻辑 |
| 参数化良好 | test_rules.py::test_classify_mistake_categories | 7 组参数覆盖四类错因 + 边界情况 |
| 隔离严格 | conftest.py | 三层 autouse fixture（数据库/云服务/LLM）互相独立，防御纵深充分 |

---

## 2. Skill 包体系

### 2.1 SKILL.md 格式与内容概要

全部 15 个 SKILL.md 采用统一的 YAML frontmatter + Markdown body 格式：

| Skill | Agent | 版本 | 核心功能 | 有提示词模板 | 有实现位置 |
|---|---|---|---|---|---|
| plan-builder | Planner | 1.0.0 | 周计划 + 每日微任务 + 安排理由 | ✅ | ✅ |
| mistake-diagnosis | Diagnoser | 1.0.0 | 四类错因归因 + 补救建议 | ✅ | ✅ |
| daily-coach | Coach | 1.0.0 | 当日提醒/鼓励/调整 | ✅ | ✅ |
| weekly-review | Reporter | 1.0.0 | 周报 + 下周重点 | ✅ | ✅ |
| knowledge-gap | Diagnoser | 2.0.0 | 先修依赖追溯 + 验证题确认 | ❌ | ✅ |
| learning-cockpit | Cockpit | 2.0.0 | 准备度评分 + 风险聚合 | ❌ | ✅ |
| risk-rescue | Coach | 2.0.0 | 五类风险识别 + 救援动作 | ❌ | ✅ |
| strategy-simulation | Simulator | 2.0.0 | 四方案对比 + 结果区间 | ❌ | ✅ |
| strategy-experiment | Reporter | 2.0.0 | 学习方式小实验 + 收益排行 | ❌ | ✅ |
| ai-panel | Panel | 2.1.0 | 四角色联合评审 + 投票 | ❌ | ✅ |
| cognitive-load | Coach | 2.1.0 | 负荷计算 + 难度动态调节 | ❌ | ✅ |
| evidence-chain | Auditor | 2.1.0 | AI 判断依据留痕 + 追溯 | ❌ | ✅ |
| freshness-radar | Reporter | 2.1.0 | 资料时效评估 + 补资料建议 | ❌ | ✅ |
| learning-probe | Diagnoser | 2.1.0 | 主动探针 + 迁移压力测试 | ❌ | ✅ |
| thought-replay | Diagnoser | 2.1.0 | 思维步骤回放 + 错误定位 | ❌ | ✅ |

### 2.2 是否被代码真实加载

**SKILL.md 文件不被代码加载**。它们是纯文档，供人阅读和答辩展示。

代码中的 Skill 注册表在 `backend/app/agents/skills.py`，是一个硬编码的 Python 列表 `SKILLS`，只包含 4 个 Skill（plan-builder、mistake-diagnosis、daily-coach、weekly-review），通过 `GET /api/skills` 暴露。**其余 11 个 Skill（knowledge-gap 到 thought-replay）没有在 skills.py 中注册**，但其对应的后端服务模块（如 `readiness.py`、`knowledge_map.py`、`probes.py` 等）确实存在且有对应测试。

换言之：15 个 SKILL.md 描述的功能在后端均有对应实现，但只有前 4 个被纳入正式的 Skill 注册表 API；后 11 个作为独立服务模块存在，通过各自的 API 端点访问，未被抽象为统一的 Skill 接口。

### 2.3 四套学科包的数据来源与规模

`skill_packages.py` 中硬编码了 4 套学科知识点包：

| 包名 | 学科 | 知识点数 | 层级深度 | 数据来源 |
|---|---|---|---|---|
| cet4 | 英语 | 20 | 2 级（6 父 + 14 子） | 硬编码 |
| kaoyan-math | 数学 | 17 | 2 级（3 父 + 14 子） | 硬编码 |
| hcia-datacom | 网络 | 16 | 2 级（4 父 + 12 子） | 硬编码 |
| computer-level2 | 计算机 | 15 | 2 级（4 父 + 11 子） | 硬编码 |

数据全部硬编码在 Python 代码中，不从外部文件加载。总计 68 个知识点，每个包含 name/parent/weight 三个字段。数据量较小，适合作为演示和比赛用途，但距离真实学科体系的完整度有明显差距。知识点权重设计合理（1.0–2.0 范围），体现了对不同考点重要程度的区分。

### 2.4 与赛题要求的匹配度

赛题要求"基于已有智能体与 Skills"。项目的 Skill 体系有以下特点：
- ✅ 有明确的 Skill 定义格式（YAML frontmatter + 规则 + 提示词模板）
- ✅ 有 Skill 注册表和 API 端点
- ✅ 有学科包市场和一键应用机制
- ⚠️ SKILL.md 是文档而非可执行规范，不被运行时加载
- ⚠️ 只有 4/15 个 Skill 在注册表中，其余以普通服务模块形式存在
- ⚠️ 学科包数据量偏小（68 个知识点），且全部硬编码

---

## 3. 部署与运维

### 3.1 Dockerfile 分析

| 阶段 | 基础镜像 | 操作 | 评价 |
|---|---|---|---|
| web | node:20-alpine | npm install + build | ✅ 使用 alpine 减小体积 |
| app | python:3.10-slim | pip install + COPY | ⚠️ 未使用多阶段优化 Python 层 |

**优点**：前端构建与后端分离；使用 `--no-cache-dir` 减少 pip 缓存；设置 `PYTHONDONTWRITEBYTECODE` 和 `PYTHONUNBUFFERED`。

**不足**：
- ❌ 未创建非 root 用户，容器以 root 运行
- ❌ 无 HEALTHCHECK 指令
- ❌ 未使用 `.dockerignore`，可能将 `.git`、`node_modules`、`.env` 等拷入构建上下文
- ❌ Python 基础镜像用 `slim` 而非 `alpine`，最终镜像体积约 400–500MB
- ⚠️ `COPY backend/app ./app` 会把 `__pycache__` 也拷入（虽有 PYTHONDONTWRITEBYTECODE 但不清理已有缓存）

### 3.2 docker-compose.yml 编排

| 服务 | 镜像 | 健康检查 | 依赖 | 评价 |
|---|---|---|---|---|
| db | mysql:8.0 | ✅ mysqladmin ping | — | ✅ utf8mb4 字符集 |
| redis | redis:7-alpine | ✅ redis-cli ping | — | ✅ AOF 持久化 |
| app | build: . | ❌ 无 | db(healthy) + redis(healthy) | ⚠️ 启动时自动 seed |

**优点**：依赖顺序正确（`condition: service_healthy`）；数据卷持久化；环境变量从宿主传入。

**不足**：
- ❌ MySQL root 密码 `rootpass` 和应用密码 `xuejipass` 硬编码在 compose 文件中
- ❌ `SECRET_KEY: please-change-this-in-production` 硬编码默认值
- ❌ app 服务无健康检查
- ❌ 端口直接映射 `8000:8000`，无反向代理
- ⚠️ 启动命令 `python -m app.seed && python run.py` 中 seed 失败会阻止应用启动

### 3.3 启动脚本

`start.bat`（Windows）和 `start.sh`（Linux）逻辑一致：检查前端 dist → npm build → pip install → seed → run.py。两者都是开发友好型脚本，适合本地一键启动。`run.py` 使用 uvicorn 启动，支持 `--reload` 和 `--host/--port` 参数。

### 3.4 环境变量清单

| 变量名 | 用途 | 默认值 | 敏感性 |
|---|---|---|---|
| SECRET_KEY | JWT 签名密钥 | `xueji-dev-secret-please-change` | 🔴 高 |
| DATABASE_URL | 数据库连接串 | sqlite 本地 | 🟡 中 |
| REDIS_URL | Redis 连接串 | 空 | 🟡 中 |
| RDS_HOST / HUAWEI_RDS_HOST | 华为云 RDS 地址 | 空 | 🟡 中 |
| RDS_PASSWORD | RDS 密码 | 空 | 🔴 高 |
| REDIS_PASSWORD / DCS_PASSWORD | Redis 密码 | 空 | 🔴 高 |
| HUAWEICLOUD_SDK_AK | 华为云 AccessKey | 空 | 🔴 高 |
| HUAWEICLOUD_SDK_SK | 华为云 SecretKey | 空 | 🔴 高 |
| LLM_BASE_URL | LLM API 地址 | 空 | 🟡 中 |
| LLM_API_KEY | LLM API 密钥 | 空 | 🔴 高 |
| LLM_MODEL | LLM 模型名 | pangu | 🟢 低 |
| CORS_ORIGINS | 跨域白名单 | localhost:5173/8080 | 🟡 中 |
| UPLOAD_DIR | 上传文件目录 | backend/uploads | 🟢 低 |
| FRONTEND_DIST | 前端构建产物路径 | ../frontend/dist | 🟢 低 |
| CLOUD_PROJECT_ID / REGION / VPC_ID / SUBNET_ID / SECURITY_GROUP_ID | 华为云资源参数 | 空 | 🟡 中 |

### 3.5 依赖锁定

`requirements.txt` 使用精确版本锁定（`==`），共 13 个直接依赖。pytest 版本为 6.2.4（较旧，2021 年发布），与 httpx 0.28.1 和 FastAPI 0.104.1 的组合可能存在兼容性隐患。未使用 `pip-tools` 或 `poetry.lock` 管理传递依赖。

### 3.6 CodeArts 痕迹

`.codeartsdoer/` 目录存在，包含：
- `rule/metadata.properties`：内容为 `projectExpert=[]`
- `mcp/mcp_settings.json`：内容为 `{"mcpServers": {}}`
- `mem-exp-config.json`、`package.json`
- `.codebase/` 子目录：含 `baseline_info.json`、`codebaseId.json`、`upload_state.json`、`file-index.db`、`codebase_embedded_file.txt`、`index_records.json`、`inc.lock/meta.json`
- `temp/accept/`：含多个 `.original.db`、`.original.png`、`.original.exe`（cloudflared）、`.coverage` 文件

这些是华为云码道 CodeArts IDE 的项目索引和会话数据，证明项目确实在 CodeArts 环境中开发过。`.codeartsdoer/` 已被 `.gitignore` 排除。

`_sdk_test/` 目录包含一个华为云 SDK wheel 文件 `huaweicloudsdkcore-3.1.221-py3-none-any.whl`，用于本地测试华为云 API 连通性。

### 3.7 云部署脚本

`backend/scripts/` 目录存在，包含两个脚本：
- `provision_cloud.py`（301 行）：华为云 RDS/DCS 自动开通脚本，支持 `--dry-run` / `--apply`，会自动生成强密码、等待实例就绪、输出连接信息
- `migrate_to_rds.py`（111 行）：SQLite → RDS 数据迁移脚本，支持 `--dry-run` / `--apply` / `--truncate`，按外键依赖顺序分批写入

两个脚本结构完整，有参数校验和错误处理，但未经真实云环境验证（`cloud-onboarding.md` 明确写"真实实例尚未创建"）。

---

## 4. 安全与合规检查

### 4.1 敏感文件状态

| 文件 | 是否存在 | .gitignore 覆盖 | 风险 |
|---|---|---|---|
| `.env` | ✅ 存在 | ✅ 已忽略 | 低（不会被提交） |
| `.env.cloud` | ✅ 存在于根目录和 backend/ | ✅ 已忽略 | 低 |
| `.env.example` | ✅ 存在 | N/A（应提交） | 低（无真实密钥） |
| `backend/uploads/` | ✅ 存在（含 1 张图片） | ✅ 已忽略 | 低 |
| `.codeartsdoer/` | ✅ 存在 | ✅ 已忽略 | 低 |
| `_sdk_test/` | ✅ 存在 | ❌ **未被 .gitignore 覆盖** | 🟡 中（SDK wheel 可能被提交） |

### 4.2 主要安全问题

| 编号 | 问题 | 严重度 | 说明 |
|---|---|---|---|
| S1 | 默认 SECRET_KEY 硬编码 | 🔴 高 | `config.py` 默认值 `xueji-dev-secret-please-change`，docker-compose.yml 中也硬编码 `please-change-this-in-production`。若部署时忘记修改，所有 JWT token 可被伪造 |
| S2 | 安全组 3306/6379 放行 0.0.0.0/0 | 🔴 高 | README 第 370 行自述"安全组 3306/6379 当前放行 0.0.0.0/0"。这意味着 RDS MySQL 和 Redis 对公网完全开放，任何知道地址的人都可以尝试连接。cloud-onboarding.md 第 158 行也提醒"不要对 0.0.0.0/0 开放"，但实际配置未修正 |
| S3 | compose 中数据库密码明文 | 🟡 中 | `MYSQL_ROOT_PASSWORD: rootpass`、`MYSQL_PASSWORD: xuejipass` 硬编码在 docker-compose.yml 中，应改用 `.env` 引用 |
| S4 | `_sdk_test/` 未被 gitignore | 🟡 中 | 华为云 SDK wheel 文件可能被意外提交，增加仓库体积且无必要 |
| S5 | Token 过期时间过长 | 🟡 中 | `ACCESS_TOKEN_EXPIRE_MINUTES` 默认 10080（7 天），对于学习类应用偏长 |
| S6 | CORS 默认只限 localhost | 🟢 低 | 生产部署时需手动添加域名，否则前端无法跨域访问 |

### 4.3 上传与日志

- 上传目录：`backend/uploads/`，已在 .gitignore 中排除
- 日志：.gitignore 排除了 `*.log`，但代码中未见显式日志文件写入配置（uvicorn 默认输出到 stdout）
- 数据库文件：`backend/*.db`、`backend/xueji.db`、`backend/smoke.db` 均已排除

---

## 5. 赛题要求对账表

| # | 赛题要求 | 达成度 | 依据 |
|---|---|---|---|
| 1 | 基于华为云产品打造 AI 创新应用 | ✅ 已达成 | 接入 RDS MySQL、DCS Redis、盘古/DeepSeek LLM；有 provision_cloud.py 自动开通脚本；有 cloud-onboarding.md 完整文档；接入中心实时显示云服务状态。但真实云实例尚未创建，目前处于"代码就绪、待凭证激活"状态 |
| 2 | 使用华为云码道 CodeArts 开发 | ✅ 已达成 | `.codeartsdoer/` 目录含完整的项目索引、代码库嵌入向量、会话数据，证明在 CodeArts IDE 中进行了实质性开发 |
| 3 | 基于已有智能体与 Skills | ⚠️ 部分达成 | 有 4 个智能体（Planner/Diagnoser/Coach/Reporter）+ 15 个 SKILL.md + 4 套学科包。但 SKILL.md 是文档不被运行时加载；只有 4/15 个 Skill 在注册表中；学科包数据量小（68 知识点）且硬编码 |
| 4 | 开通并关联 RDS、Redis | ⚠️ 部分达成 | 代码侧完整支持 RDS/Redis 自动接入、探活、降级；有开通脚本和迁移脚本。但 README 自述"真实实例尚未创建"，当前运行在 SQLite + 内存缓存模式 |
| 5 | 云上快速部署 | ⚠️ 部分达成 | Dockerfile + docker-compose.yml + start.sh/bat 构成完整部署链；有华为云 ECS 部署文档。但 Dockerfile 缺少非 root 用户和健康检查；compose 中密码硬编码；无 CI/CD 流水线 |
| 6 | 入围后开源 | ⚠️ 部分达成 | .gitignore 覆盖了 .env/.env.cloud/uploads/.codeartsdoer 等敏感文件；但 `_sdk_test/` 未被忽略；默认密钥硬编码在代码和 compose 中；安全组 0.0.0.0/0 问题需在开源前解决 |
