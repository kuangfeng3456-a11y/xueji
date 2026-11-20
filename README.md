# 学迹 · 自适应 AI 学习教练

> 以「学习状态数据」为核心，用四个智能体和可复用 Skills 生成、执行并动态调整个人学习计划的 AI 学习教练。
>
> 第十一届华为 ICT 大赛创新赛 · 赛题一（基于华为云产品打造 AI 创新应用）

## 项目定位

目标用户是有明确考试或认证目标的大学生（四六级、考研、计算机等级、HCIA 等）。学迹解决四个痛点：

- **有资料没计划**：不知道每天该学什么、学多少；
- **计划坚持不下去**：一次性生成的计划，落后一次就作废；
- **错题不复盘**：只记录答案，不分析为什么错；
- **通用对话 AI 不了解你**：每次都要重新交代背景，给不出连续指导。

核心闭环：**生成 → 执行 → 反馈 → 重排**。落后、错题增多、临近考试时自动调整，并给出调整理由。

## 已实现功能（P0 全部完成）

| 功能 | 实现说明 |
| --- | --- |
| 目标设定 | 考试名称、考试日期、每日可用分钟，支持多目标切换 |
| 资料导入 | 粘贴文本或上传 txt / md / csv / docx / pdf，自动抽取知识点树 |
| 计划生成 | 按倒计时、每日时长与知识点优先级生成周计划与每日 3 个微任务 |
| 每日任务与打卡 | 任务带类型、时长、优先级与「为什么今天安排这个」的理由 |
| 做题与错题录入 | 文本录入题目、我的答案、正确答案，关联知识点 |
| 错题归因 | 概念不清 / 方法不会 / 粗心 / 时间不够四类，对应四种补救建议 |
| 动态重排 | 任务逾期自动顺延、超时长自动推迟。拍题、随堂测答错或闪卡没记住时，会把该知识点排成今天的「针对弱项」；同一知识点 7 天内错题达到 2 道时，仍会插入补救任务 |
| 周报复盘 | 完成率、掌握度变化、错题分布、下周重点，可生成历史周报 |
| 学习节奏画像 | 统计常学时段、平均拖延天数、近 28 天完成率；完成率过低时计划自动降为每日 2 个任务 |
| 数据导出与删除 | `GET /api/auth/me/export` 导出全量 JSON，`DELETE /api/auth/me` 注销账号并清空全部数据 |
| 班级看板（P1） | 邀请码建班 / 加班，成员画像（连续打卡、7 天完成率、平均掌握度、最薄弱点）、群体薄弱知识点、活跃人数与成员排行 |
| 学习搭子（P1） | 按用户名互加好友、双向解除，按连续打卡 / 完成率 / 掌握度排序的搭子榜 |
| 语音问答（P1） | 规则优先的教练问答：倒计时、薄弱点、今日任务、复习间隔、错题分布、计划可行性、拖延鼓励；配置 LLM 后自动润色 |
| 学科 Skill 包 | 内置四六级、六级、考研数学、考研英语、HCIA-Datacom、计算机二级 Python、数据结构、操作系统、计算机网络、离散数学、大学物理、C 语言、马克思主义基本原理、软件工程。学生只能导入已通过审核的包。教师提交的自定义包需另一位教师或教务审核，分享后学生才能使用 |
| 自动时间调整 | 进入首页自动检查逾期、空计划与临考状态；剩余 ≤ 7 天自动提高复习密度，无需手动点重排 |
| 强制学习 | 目标级强制模式：任务不可跳过；专注不足计划时长 60% 或离开页面 3 次会记违约；今日任务全部完成才解锁 |
| 摄像头监督 | 浏览器摄像头每 60 秒抓拍学习见证；错题录入支持摄像头拍照；无摄像头环境自动降级为文件上传 |
| DeepSeek 全链路 | Planner / Diagnoser / Coach / Reporter、知识点抽取与语音问答全部接入 DeepSeek，无 Key 时自动规则兜底 |
| 学情洞察 | 12 周学习热力图、五维能力雷达、疲劳指数与干预建议、8 枚成就徽章 |
| 冲刺模拟器 | 基于记忆曲线预测考试日掌握度，模拟当前 / 减负 / 冲刺三情景并反推所需每日时长 |
| 闪卡复习 | 知识点翻转卡 + 1/2/4/7/15 天间隔重复，记得 / 忘记实时更新掌握度。错题可加入今日复习；记住且掌握度不低于 0.5 时，今天的补练标为完成，下次仍按上述间隔出现 |
| AI 随堂测 | DeepSeek 现场出题 → 服务端判分 → 四类错因归因 → 错题入库 → 自动重排闭环 |
| 白噪音专注 | 雨声 / 咖啡厅 / 432Hz 纯音由 Web Audio 实时合成，无需音频资源 |
| 全网络与模型接入 | 学情诊断、冲刺策略、闪卡释义也接入 DeepSeek；新增「系统接入」页展示并一键测试模型、数据库、缓存、存储、语音与摄像头 |
| 学习驾驶舱 | 准备度评分（知识覆盖 × 时间负荷 × 风险扣分）、风险提示、今日关键任务与快捷入口 |
| 学习数字孪生 | 知识热力矩阵、错因分布、近 8 周行为趋势与策略偏好排行 |
| 知识漏洞地图 | 先修依赖图、候选漏洞追溯、DeepSeek 验证题确认，确认后自动生成修复任务 |
| 未来模拟实验室 | 维持现状 / 增加时间 / 优先修复漏洞 / 组合策略四种方案，展示结果区间、负荷与不确定性 |
| 风险救援中心 | 知识、时间、执行、记忆、策略五类风险，确认后自动调整并对比今日任务前后变化 |
| 策略实验室 | 精读、刷题、闪卡、AI 讲解四类学习方式的 3 天小实验与个人收益排行 |
| AI 主动探针出题官 | 主动寻找隐藏知识盲区，按掌握度与错题自动选题，支持探针 / 迁移 / 挑战三类模式 |
| 思维路径回放器 | 把错题拆成 3–5 个思维步骤，标出错误发生的步骤与原因 |
| 知识迁移压力测试 | 换情境、换问法生成迁移题，判断是否真正理解并能应用 |
| 多智能体学习评审团 | 计划官、诊断官、风险官、教练四角色协作审查，输出意见与投票裁决 |
| 学习内容时效雷达 | 评估资料年份、考纲覆盖与内容完整度，标记可能过时的资料 |
| 认知负荷调节器 | 结合疲劳、任务量与错题率计算负荷，自动降载或加难 |
| 反脆弱挑战模式 | 用陌生条件训练应对能力，答错不扣掌握度，记录韧性值 |
| 学习证据链 | 每个 AI 判断记录输入、规则、输出与模型来源，可逐条展开追溯 |
| 拍题与语音 | 错题可拍照或从相册上传，调用 `POST /api/cloud/ocr/extract`。语音输入走 `POST /api/cloud/sis/recognize`，播报走 `POST /api/cloud/sis/synthesize`。未配置华为云凭证、缺少 SDK 或调用失败时返回 `not_configured` / `sdk_missing` / `error`，文本为空，并说明改用手动填写、本机听写或本机朗读。不会把失败说成识别成功 |
| 多轮语音教练 | `POST /api/coach/sessions` 保存会话和历史。追问会接上一条问题。语音页带上今天的下一步；已有弱项时，开场问题对着那个知识点。`POST /api/coach/sessions/{id}/close` 给出不超过 3 条要点，并把提到的知识点排进今日补练 |
| 口语练习阶梯 | 同一句内容按听懂、跟读、遮词、复述、复习推进。跟读仍有词级高亮。遮住的词可以点开。复述进入教练。难点可放入今日闪卡，复习间隔仍是 1/2/4/7/15 天 |
| 今日路径 | 看课、随堂测、口语与追问、复盘四步写入 `loop_steps`。完成对应记录后该步变为已完成，`next_step` 改为下一项。答错学生和未暴露弱项的学生，今日任务和下一步不同 |
| 今日复盘与周报 | 今日复盘列出已完成任务、仍然较弱的知识点和下一步，数据来自当天任务与掌握度。周报仍按本周任务、掌握度变化和错题统计生成 |
| 鸿蒙客户端 | `clients/harmonyos/` 是 HarmonyOS Stage 模型 ArkTS 工程，复用上述 FastAPI。用 DevEco Studio 打开该目录即可同步构建。本仓库的 CI 只跑后端测试和前端构建，不编译 HAP |
| 教师工作台与班级报表 | 教师、教务注册后可见。工作台可从已通过的学科包布置练习，学生今日会出现「教师布置」任务；做完后班级完成度按真实完成人数计算。班级报表对比完成率、平均掌握和弱项。未配置 `ACADEMIC_BRIDGE_URL` 时，教务名册是内置样例，页面标明样例对照，不连接真实学校 |



## 竞品能力对齐与差异化创新

竞品常见能力已覆盖：番茄专注、白噪音、学习热力图、闪卡与间隔重复、错题本、AI 出题、学习报告、打卡排行、班级看板、学习计划。

学迹的差异化创新：

1. **考试日掌握度预测（冲刺模拟器）**：不只告诉你今天学什么，还预测「按当前投入，考试日能达到什么水平」，并反推达成目标所需的每日时长，可一键应用并重排。
2. **状态感知的疲劳干预**：把专注中断、离开页面、错题增长、连续学习天数合成疲劳指数；疲劳偏高时一键把今日任务降到 1 个，其余自动顺延。
3. **AI 随堂测闭环**：出题、判分、四类错因归因、错题入库、掌握度更新、计划重排一次完成，不是孤立的刷题工具。
4. **强制学习 + 摄像头学习见证**：目标级强制模式，任务不可跳过；摄像头每 60 秒抓拍学习见证，隐私优先，不做人脸识别。
5. **可解释的规则内核**：预测、排程、掌握度全部来自可复算规则，大模型只负责语义与表达，答辩时可逐条解释。

学迹 2.0 进一步加入五项「决策级」创新（来自 11.docx）：

6. **学习驾驶舱**：把「准备度」作为统一指标，综合高权重知识覆盖、时间负荷、漏洞、逾期与违约，一屏回答「现在到底稳不稳」。
7. **知识漏洞地图**：从错题沿先修依赖向上追溯，先列候选漏洞，再用验证题确认，避免把时间花在错误的知识点上。
8. **未来模拟实验室**：同时比较四种策略方案，展示结果区间、每日负荷与不确定性，不做单点成绩承诺。
9. **风险救援中心**：五类风险各自给出触发原因、建议动作和调整前后对比，用户确认后才改计划。
10. **策略实验室**：用 3 天小实验比较精读、刷题、闪卡与 AI 讲解的个人收益，把「哪种方法适合我」变成可测量数据。

学迹 AI 决策增强（来自最新创新清单）：

11. **AI 主动探针出题官**：不再等用户提问，AI 主动按掌握度与错题选题，寻找隐藏盲区。
12. **思维路径回放器**：把错题拆成思维步骤，定位「在哪一步想错了」，而不只是给正确答案。
13. **知识迁移压力测试**：换情境、换问法，判断学生是否真正理解并能应用。
14. **多智能体学习评审团**：四个角色分别从计划、诊断、风险、教练视角审查，再汇总裁决。
15. **学习内容时效雷达**：识别资料年份与考纲缺口，防止用旧资料备考。
16. **认知负荷调节器**：根据疲劳、任务量与错题率动态调整难度与任务颗粒度。
17. **反脆弱挑战模式**：用陌生条件训练应对能力，答错不扣掌握度，只记录韧性。
18. **学习证据链**：每个 AI 判断都保留数据快照、规则与模型来源，可逐条追溯。

## 技术架构

```
┌──────────────────────────── 浏览器 ────────────────────────────┐
│  Vue 3 + Vue Router（Hash）· 单页应用，由后端同源托管           │
│  今日 / 计划 / 错题 / 周报 / 目标资料 / Skills / 班级 / 搭子 / 语音 / 市场 │
└───────────────────────────────┬────────────────────────────────┘
                                │ /api
┌───────────────────────────────▼────────────────────────────────┐
│  FastAPI · JWT 鉴权 · 统一错误处理                              │
│                                                                │
│  Agent 层：Planner ─ Diagnoser ─ Coach ─ Reporter               │
│  Skill 层：plan-builder / mistake-diagnosis /                   │
│             daily-coach / weekly-review                         │
│  学科包：cet4 / cet6 / kaoyan-math / kaoyan-english 等        │
│  规则层：掌握度、复习间隔、任务优先级、时长分配、周报统计       │
│  模型层：DeepSeek（OpenAI 兼容，可切换盘古 / ModelArts）        │
└──────┬──────────────────┬──────────────────┬───────────────────┘
       │                  │                  │
   RDS MySQL          DCS Redis             OBS
  （SQLite 可切换）  （内存缓存可降级）   （资料与错题图片）
```

**关键设计**：大模型只负责理解语义和生成文字；排程、掌握度、复习间隔、周报统计全部由程序规则完成，结果稳定、可复现，避免幻觉影响事实。学习画像有两个维度：掌握度回答“你会什么”，学习节奏（常学时段、拖延规律、完成率）回答“你怎么学”，每日任务数会随近期完成率自动调整。

### 核心规则

| 规则 | 公式 / 策略 |
| --- | --- |
| 掌握度更新 | `m_new = m_old + 0.3 × (r − m_old)`，答对 `r=1`，答错 `r=0` |
| 复习间隔 | `1 / 2 / 4 / 7 / 15` 天，答错回到 1 天 |
| 任务优先级 | `权重 × (1 − 掌握度) × 临近系数` |
| 临近系数 | `1 + 3 × e^(−剩余天数 / 14)` |
| 每日负载 | 任务总时长不超过每日可用分钟，超出按优先级推迟到后一天 |
| 错因触发 | 同一知识点 7 天内错题 ≥2 道，插入 20 分钟补救任务 |
| 周报 | 完成率 = 完成数 / 任务总数；掌握度变化 = 当前均值 − 周初快照均值 |

## 目录结构

```
.
├── backend/
│   ├── app/
│   │   ├── agents/          # Planner / Diagnoser / Coach / Reporter + Skills 注册表
│   │   ├── api/             # auth / goals / plan / learning / dashboard / social / coach / skill_market
│   │   ├── services/        # 规则引擎、计划与重排、资料解析、周报、掌握度、学习节奏、问答、班级、Skill 包
│   │   ├── config.py        # 环境变量配置
│   │   ├── models.py        # users / goals / knowledge_points / mastery / tasks / classes / buddies / skill_packages ...
│   │   ├── llm.py           # OpenAI 兼容 LLM 客户端（无 Key 自动规则兜底）
│   │   ├── cache.py         # Redis / 内存双后端缓存与限流
│   │   ├── main.py          # FastAPI 入口，托管 frontend/dist
│   │   └── seed.py          # 演示数据（含同伴、班级、学习搭子）
│   ├── tests/               # 规则、服务层与接口测试（pytest）
│   ├── run_coverage.py      # 基于 stdlib trace 的行覆盖率统计
│   ├── requirements.txt
│   └── run.py               # 启动脚本（修复 Windows 事件循环）
├── frontend/
│   ├── src/
│   │   ├── views/           # 11 个页面（含班级看板、学习搭子、语音问答、Skill 市场）
│   │   ├── components/      # TaskCard / GoalSwitcher
│   │   ├── api.js · store.js · router.js · App.vue · style.css
│   ├── build.mjs            # Rollup + Vue SFC 编译（不依赖 esbuild）
│   └── package.json
├── clients/harmonyos/       # 鸿蒙 ArkTS 客户端（DevEco Studio 打开）
├── skills/                  # 四个可复用学习类 Skills（独立学科包）
├── Dockerfile               # 多阶段：构建前端 + 运行后端
├── docker-compose.yml       # MySQL + Redis + 应用
├── .env.example
├── start.bat / start.sh
└── README.md
```

## 快速开始（Windows）

前置：Python 3.9+、Node.js 18+。

```bat
:: 1. 构建前端
cd frontend
npm install --no-audit --no-fund
npm run build

:: 2. 安装后端依赖（建议使用虚拟环境）
cd ..\backend
python -m pip install -r requirements.txt

:: 3. 生成演示数据并启动
python -m app.seed
python run.py --port 8000
```

打开 <http://127.0.0.1:8000>，用 `python -m app.seed` 输出的账号登录（默认用户名 `demo`，口令由脚本生成并打印）。

也可直接双击根目录的 `start.bat`。若 8000 端口被占用，改用 `python run.py --port 8080`。

> 前端构建使用 Rollup + Vue 官方编译器，不依赖 esbuild；构建产物 `frontend/dist` 由 FastAPI 同源托管，无需单独启动前端服务。
> 修改前端源码后重新执行 `npm run build` 即可。

## 演示流程（对应 3–5 分钟视频）

1. **痛点引入（30 秒）**：首页展示考试倒计时、今日任务、教练提醒与「为什么这样安排」。
2. **生成计划（60 秒）**：进入「目标与资料」查看知识点树 → 「学习计划」生成 7 天计划，展开任务理由。
3. **错题重排（90 秒）**：在「错题与掌握度」录入两道同知识点错题 → 展示四类错因归因 → 第二次提交后出现「插入补救任务」的重排说明。
4. **周报复盘（45 秒）**：生成周报，展示完成率、掌握度变化和下周重点。
5. **架构与部署（45 秒）**：Skills 页展示四个智能体的职责边界、三条核心规则与运行环境（LLM / Redis 状态）。
6. **强制学习（可选）**：在「目标与资料」开启强制模式 → 进入「强制学习」，选择任务、打开摄像头，倒计时结束自动打卡；中途离开会记录违约。
7. **洞察与冲刺（可选）**：学情洞察看热力图 / 雷达 / 疲劳；冲刺模拟器比较三情景并应用推荐时长；闪卡复习与 AI 随堂测展示间隔重复与出题闭环。
8. **群体与拓展（可选）**：班级看板展示同伴薄弱点，语音问答演示一句话查今日任务，Skill 市场一键导入考研数学包。

## 环境变量

复制 `.env.example` 为 `.env`（或直接设置系统环境变量）。后端启动时会自动读取项目根目录与 `backend/` 下的 `.env`：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///backend/xueji.db` | 生产改为 `mysql+pymysql://user:pass@rds:3306/xueji?charset=utf8mb4` |
| `REDIS_URL` | 空 | 配置后自动启用 Redis 缓存、诊断限流；失败自动降级内存缓存 |
| `LLM_BASE_URL` | 空 | DeepSeek 使用 `https://api.deepseek.com/v1`；也可填盘古 / ModelArts 网关 |
| `LLM_API_KEY` | 空 | 未配置时所有 Agent 自动使用规则兜底；配置后全链路启用大模型 |
| `LLM_MODEL` | `pangu` | DeepSeek 推荐 `deepseek-chat` |
| `QUESTION_BANK_API_URL` | 空 | 可选外部单选题库服务 POST 地址（按知识点返回题目）；只在服务端请求，配置后对内置库题量不足的对应知识点优先查询 |
| `QUESTION_BANK_API_KEY` | 空 | 外部题库 Bearer Token，仅服务端持有，不会下发浏览器 |
| `QUESTION_BANK_TIMEOUT` | `8` 秒 | 外部题库请求超时；失败时回退内置题库 / 模型 / 规则 |
| `QBANK_PROVIDER` | `lemtk` | 查题供应商：`lemtk`（柠檬题库）/ `gomooc`（ZERO 网课题库） |
| `QBANK_GOMOOC_BASE_URL` | `https://api.gomooc.net` | ZERO 题库域名（备用同源 `https://api2.gomooc.net`） |
| `QBANK_GOMOOC_ENDPOINT` | `/api.php` | ZERO 题库接口路径，`GET ?token=&question=` |
| `QBANK_GOMOOC_TOKEN` | 空 | ZERO 题库 Token（**必填**，该接口没有免 token 通道；额度用尽返回 `code 429`） |
| `QBANK_GOMOOC_MERGE_OPTIONS` | `true` | 首轮未命中时是否把选项按 `A. xx` 拼进题干再查一次 |
| `QBANK_FALLBACK_PROVIDER` | 空 | 主供应商给不出答案（额度用尽 / Token 失效 / 超时 / 暂无答案）时自动回落的备用供应商，留空则不降级 |
| `QBANK_BASE_URL` | 空 | 第三方查题题库域名（如 `https://api.lemtk.xyz`，备用 `https://api.vanse.top`）；按题干 + 选项查答案，不参与按知识点出题 |
| `QBANK_TOKEN` | 空 | 查题接口 Bearer Token；普通查询 `cx` 可留空（免费限流），高级查询 `mcx` 必填 |
| `QBANK_EMAIL` | 空 | 题库注册邮箱，仅余额查询 `/api/v1/balance` 使用 |
| `QBANK_MODE` | `cx` | `cx` 普通查询 / `mcx` 高级查询（命中更高，需 Token） |
| `QBANK_TIMEOUT` | `8` 秒 | 查题接口请求超时（秒） |
| `SECRET_KEY` | 开发默认值 | JWT 签名密钥，生产必须修改 |
| `CORS_ORIGINS` | 本地开发地址 | 逗号分隔 |
| `FRONTEND_DIST` | `../frontend/dist` | 前端构建产物目录 |
| `UPLOAD_DIR` | `backend/uploads` | 错题图片与学习见证存储目录，可替换为 OBS 挂载路径 |

> 安全提示：`.env` 已加入 `.gitignore`，请勿提交密钥。单元测试会强制清空 LLM 配置，避免调用真实 API 产生费用。

> 外部题库接口约定：配置 `QUESTION_BANK_API_URL` 后，服务端发送 `{exam_name, knowledge_point, module, count, language, question_type}` JSON，并接受 `{ "questions": [{ "question", "options": ["A","B","C","D"], "answer_index", "explanation", "kp_name" }] }`。返回题会校验题干语言、选项数、答案下标与重复选项；无效响应不会进入题目缓存。当前不预置第三方供应商或密钥，需要自行选择有授权的题库服务并配置。

> 查题题库约定：`QBANK_*` 对接的是「按题干查答案」类接口，输入题干 + 选项返回答案，用于核验已有题目；它们不按知识点枚举题目，因此不进入上面的出题降级链。目前内置两家适配器（`backend/app/services/qbank_provider.py`）：
>
> - `lemtk`：柠檬题库 / LIKE知识库同款（`POST /api/v1/cx`、`/api/v1/mcx`、`GET /api/v1/balance`），普通查询可免 Token；
> - `gomooc`：ZERO 网课题库（`GET /api.php?token=&question=`），必须带 Token，额度用尽返回 `code 429`，没有余额查询接口。
>
> 用 `QBANK_PROVIDER` 选主供应商，`QBANK_FALLBACK_PROVIDER` 配备用供应商即可自动降级；返回的 metadata 里 `provider` / `path` / `primary_status` 会如实说明这次答案来自谁、主供应商为什么没答上。lemtk 的详细说明见 `backend/CHAOXING_INTEGRATION_GUIDE.md`。

## 主要 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` `/api/auth/login` | 注册 / 登录，返回 JWT |
| GET/POST | `/api/goals` | 目标列表 / 创建目标 |
| POST | `/api/goals/{id}/materials/text` · `/upload` | 资料导入与知识点抽取 |
| GET | `/api/goals/{id}/knowledge-points` | 知识点树与掌握度 |
| POST | `/api/goals/{id}/plan` | 生成计划（`days`、`regenerate`） |
| GET/PATCH | `/api/goals/{id}/tasks` · `/api/goals/tasks/{taskId}` | 任务查询与打卡 |
| POST | `/api/goals/{id}/replan` | 动态重排，返回变化说明 |
| POST/GET | `/api/goals/{id}/mistakes` | 错题录入（自动归因 + 重排）/ 列表 |
| POST | `/api/goals/{id}/mastery/{kpId}/answer` | 自测答对/答错，更新掌握度与复习日期 |
| POST/GET | `/api/goals/{id}/reports` | 生成 / 查看周报 |
| GET | `/api/goals/{id}/rhythm` | 学习节奏画像（常学时段、拖延规律、完成率） |
| GET | `/api/auth/me/export` | 导出当前用户全部学习数据（JSON） |
| DELETE | `/api/auth/me` | 删除账号与全部学习数据 |
| GET/DELETE | `/api/auth/sessions` · `/api/auth/sessions/{id}` | 登录设备列表 / 让指定设备下线 |
| POST | `/api/auth/sessions/revoke-others` · `/api/auth/logout` | 退出其他设备 / 退出当前设备（服务端撤销会话） |
| PUT/POST | `/api/auth/security/questions` · `/api/auth/security/codes` | 设置密保问题 / 生成一次性恢复码 |
| GET/POST | `/api/auth/recovery/options` · `/api/auth/recovery/verify` · `/api/auth/recovery/reset` | 自助找回密码：查询可用方式 / 验证并取票据 / 重设密码 |
| GET | `/api/dashboard` | 首页聚合数据 |
| GET | `/api/skills` `/api/meta` | Skills 注册表 / 运行环境 |
| GET/POST | `/api/classes` · `/api/classes/join` | 班级列表 / 创建班级 / 邀请码加入 |
| GET | `/api/classes/{id}/dashboard` | 班级看板：成员画像、群体薄弱点、完成率与活跃人数 |
| POST/DELETE | `/api/classes/{id}/leave` · `/api/classes/{id}` | 退出班级 / 删除班级（仅创建者） |
| DELETE | `/api/classes/{id}/members/{memberId}` | 移除成员（仅创建者） |
| GET | `/api/users/search` | 按用户名 / 昵称搜索同学 |
| GET/POST/DELETE | `/api/buddies` · `/api/buddies/{id}` | 学习搭子列表 / 添加 / 解除 |
| POST | `/api/coach/ask` | 语音问答：规则优先，配置 LLM 后自动润色 |
| GET | `/api/skill-packages` | 学科 Skill 包列表与已应用进度 |
| POST | `/api/skill-packages/{slug}/apply` | 一键导入学科知识点包 |
| POST | `/api/goals/{id}/auto-adjust` | 按剩余时间自动调整：顺延逾期、补今日计划、临考冲刺复习 |
| POST | `/api/focus/start` · GET `/api/focus/active` | 开始强制学习 / 查询进行中的专注 |
| POST | `/api/focus/{id}/heartbeat` | 上报离开页面次数，超过 3 次自动中止并记违约 |
| POST | `/api/focus/{id}/snapshot` | 上传摄像头学习见证 |
| POST | `/api/focus/{id}/finish` · `/abort` | 完成专注并打卡 / 中止并记录违约 |
| GET | `/api/focus/history` | 最近专注记录 |
| GET | `/api/goals/{id}/violations` | 违约记录列表 |
| GET | `/api/goals/{id}/insights` | 学情洞察：热力图、能力雷达、疲劳指数、成就徽章 |
| GET | `/api/goals/{id}/forecast` | 冲刺预测（可传 `daily_minutes` 模拟不同投入） |
| POST | `/api/goals/{id}/apply-forecast` | 应用推荐每日时长并重排计划 |
| POST | `/api/goals/{id}/rest` | 疲劳降载：保留 1 个任务，其余顺延 |
| GET | `/api/goals/{id}/flashcards` | 闪卡队列（到期优先、薄弱优先） |
| GET | `/api/goals/{id}/flashcards/{kpId}/explain` | DeepSeek 生成释义、记忆技巧与常见误区 |
| POST | `/api/goals/{id}/flashcards/{kpId}/review` | 记得 / 忘记，更新掌握度与复习间隔 |
| POST | `/api/goals/{id}/quiz/generate` | DeepSeek 现场出题，服务端缓存答案 |
| GET | `/api/goals/{id}/question-banks` | 当前目标每个知识点的题库覆盖、题源与服务状态 |
| POST | `/api/goals/{id}/question-banks/test` | 对当前知识点对应的外部题库服务执行真实探测 |
| GET | `/api/goals/{id}/quiz/history` | 服务端持久化随堂测历史与统计 |
| POST | `/api/goals/{id}/quiz/submit` | 判分、错因归因、错题入库、自动重排 |
| GET | `/api/integrations` | 接入状态：模型、数据库、缓存、存储、语音、摄像头 |
| POST | `/api/integrations/test` | 逐项真实探活并返回状态与延迟 |
| GET | `/api/prompts` | 提示词中心：P00–P18 摘要、档位、版本哈希与流式标记 |
| GET | `/api/prompts/{id}` | 单条提示词正文、User 模板、输出契约与校验规则 |
| GET/POST | `/api/prompts/versions` · `/prompts/sync` | 版本注册表内容 / 幂等同步 |
| GET | `/api/prompts/{id}/cases` | 该提示词的评测用例（normal / boundary / adversarial） |
| GET | `/api/safety-events` | 安全事件（注入拦截、危机转介，只记类型不存原文） |
| GET | `/api/goals/{id}/coach/stream` | SSE 流式教练（P07）：stage / delta / result / fallback 四类事件 |
| POST | `/api/goals/{id}/socratic/stream` | SSE 流式讲解（P06），校验通过后才展示 |
| POST | `/api/voice/ask/stream` | SSE 流式语音教练（P15），失败回退一次性接口 |
| GET | `/api/events/routes` · `/api/events/recent` | 事件路由表与最近事件（总教练 event-router，文档 7.5） |
| GET | `/api/goals/{id}/reports/latest/export` | 导出最新周报：JSON 内含 AI 标识与内容编号，响应头带 X-AI-* |
| GET | `/api/cloud/services` | 华为云能力（OCR/SIS/OBS/DEW）配置与 SDK 就绪状态 |
| GET | `/api/llm-calls` | 模型调用审计：成功率、兜底率、延迟、按提示词分布与最近调用 |
| GET | `/api/goals/{id}/cockpit` | 学习驾驶舱：准备度、风险、关键任务与漏洞统计 |
| GET | `/api/goals/{id}/knowledge-graph` | 知识依赖图、候选漏洞与已验证漏洞 |
| POST | `/api/gaps/{gapId}/verify` | DeepSeek 生成漏洞验证题 |
| POST | `/api/gaps/{gapId}/submit` | 验证判分：通过则排除，失败则确认并生成修复任务 |
| GET | `/api/goals/{id}/simulate` | 未来模拟：四种策略方案、结果区间与负荷 |
| GET | `/api/goals/{id}/risks` | 五类备考风险与建议动作 |
| POST | `/api/goals/{id}/risks/{code}/resolve` | 确认风险救援并返回前后准备度与今日任务对比 |
| GET/POST | `/api/goals/{id}/experiments` | 策略实验列表 / 创建实验 |
| POST | `/api/experiments/{experimentId}/finish` | 结束实验并记录即时、延迟测试与收益 |
| GET | `/api/goals/{id}/twin` | 学习数字孪生：知识矩阵、错因、趋势与策略偏好 |
| GET/POST | `/api/goals/{id}/probes` · `/probes/generate` | 探针 / 迁移 / 挑战题列表与 AI 主动生成 |
| POST | `/api/probes/{probeId}/submit` | 作答探针或挑战，写入掌握度、韧性与证据链 |
| GET/POST | `/api/mistakes/{mistakeId}/trace` | 思维路径回放 |
| GET/POST | `/api/goals/{id}/panel/reviews` · `/panel/review` | 多智能体评审历史与发起评审 |
| GET/POST | `/api/goals/{id}/freshness` · `/freshness/scan` | 资料时效报告与扫描 |
| GET | `/api/goals/{id}/evidence` | 学习证据链（按类型筛选） |
| GET/POST | `/api/goals/{id}/cognitive-load` · `/apply` | 认知负荷查询与自动调节 |
| GET | `/api/health` | 健康检查 |

完整交互式文档：<http://127.0.0.1:8000/docs>

## 测试

```bash
cd backend
python -m pytest -q          # 636 passed + 1 skipped
python run_coverage.py       # 生成行覆盖率报告，当前约 98%（门槛 80%）
```

覆盖核心规则（掌握度、复习间隔、优先级、错因分类、连续打卡）、学习节奏画像、
计划生成与动态重排、周报统计、资料解析、Agent 规则兜底、缓存降级、
全部接口（含鉴权、错误分支、限流、数据导出与删除）。
新增模块同样全覆盖：班级看板与学习搭子（`app/api/social.py`、`app/services/social.py`）、
语音问答（`app/api/coach.py`、`app/services/qa.py`）、
学科 Skill 包市场（`app/api/skill_market.py`、`app/services/skill_packages.py`）。

> 说明：Starlette 0.27 的 `TestClient` 与 httpx 0.28 不兼容，测试使用
> `httpx.ASGITransport` 直接驱动 ASGI 应用；覆盖率由 `run_coverage.py`
> 基于标准库 `trace` 统计（同时跟踪 FastAPI 同步路由所在的线程池）。

## Docker / 华为云部署

```bash
docker compose up -d --build
```

`docker-compose.yml` 会启动 MySQL、Redis 与应用，并自动生成演示数据。生产映射：

| 方案组件 | 华为云服务 |
| --- | --- |
| 业务数据库 | RDS for MySQL |
| 缓存 / 限流 / 排行 | DCS for Redis |
| 资料与错题图片 | OBS |
| 初赛演示环境 | ECS + Docker Compose |
| 总决赛扩容 | CCE + ELB + 公网域名 |
| 大模型 | 盘古大模型 / ModelArts（以赛事发放资源为准） |
| AI 编码 | 华为云码道 CodeArts 代码智能体 |

### 华为云 RDS / DCS Redis 真实接入

应用已支持真实云连接：

- **RDS MySQL**：设置 `RDS_HOST`、`RDS_PORT`、`RDS_USER`、`RDS_PASSWORD`、`RDS_DATABASE` 后自动拼接 `DATABASE_URL`；连接池 `pool_size=10`、`max_overflow=20`、`pool_recycle=1800`，可选 `RDS_SSL_CA`。
- **DCS Redis**：设置 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`REDIS_SSL` 后自动拼接 `REDIS_URL`；支持 SSL CA、健康检查与连接池，连接失败自动降级内存缓存。
- **接入中心**：`系统接入` 页真实探活 RDS（`SELECT VERSION()`）与 Redis（读写 + 版本/内存），并显示延迟。

开通步骤（需要华为云凭证与 VPC 资源）：

```bash
cd backend

# 1. 配置环境变量（不要提交到版本库）
#    HUAWEICLOUD_SDK_AK / HUAWEICLOUD_SDK_SK / CLOUD_PROJECT_ID
#    CLOUD_REGION=cn-north-4
#    CLOUD_VPC_ID / CLOUD_SUBNET_ID / CLOUD_SECURITY_GROUP_ID
#    DCS_SPEC_CODE（DCS 控制台中的 Redis 规格编码）

# 2. 查看计划，不创建资源
python scripts/provision_cloud.py --dry-run

# 3. 真实创建 RDS MySQL + DCS Redis（会产生费用）
python scripts/provision_cloud.py --apply

# 4. 合并 .env.cloud 到 .env，迁移演示数据
python scripts/migrate_to_rds.py --dry-run
python scripts/migrate_to_rds.py --apply

# 5. 重启服务并验证
python run.py --port 8080
```

验证标准：

- `系统接入` 页 RDS / Redis 状态为「正常」，显示延迟与版本。
- 登录、计划、错题、周报、强制学习与 AI 功能全部读写 RDS。
- 缓存命中与限流走 DCS Redis（`cache_backend=redis`）。

> 当前状态（2026-11-07）：
> - **RDS 已真实创建并完成迁移验证**：cn-north-4 的 RDS MySQL 8.0 单机实例曾进入 ACTIVE，`xueji` 库完成 24 张表迁移与逐表行数校验；应用切换后登录、目标、看板与写入回查均通过。
> - **RDS 当前处于 FROZEN**：实例被华为云置为冻结，公网连接超时，API 解冻返回 `DB instance frozen`。应用启动时会自动检测并回退本地 SQLite，`/api/health` 返回 `database=sqlite-fallback`，登录与演示功能保持可用；「系统接入」显示数据库「降级运行」。解冻需在华为云控制台处理（欠费/安全冻结），解冻后重启服务会自动优先使用 RDS，无需改代码。
> - **DCS Redis 已创建但公网未接通**：主备实例 RUNNING、IP 白名单已放行本机出口 IP，但该账号/区域的公网绑定接口持续返回 `DCS.4005`；应用当前 Redis 降级为内存缓存（`cache_backend=memory`），未宣称 Redis 已接入。
> - 完成 Redis 的方式：在 DCS 控制台开启公网访问并绑定 EIP，或在同 VPC 创建 ECS 做 6379 端口跳板；之后设置 `REDIS_HOST / REDIS_PORT / REDIS_PASSWORD` 重启。
> - RDS、DCS、EIP 均为计费资源；安全组 3306/6379 当前放行 `0.0.0.0/0`，演示结束后请收紧或释放。
>
> 准备清单、控制台路径、权限与填写模板见 [docs/cloud-onboarding.md](docs/cloud-onboarding.md)。

## 界面：五个业务入口 + 内部工具区，模块按受众分级

侧边栏按 `audience` 分级。学生只看到 `core`。教师、教务和超级管理员另外看到 `campus`。标成 `internal` 的模块不进导航，仍可用深链打开。

| 入口 | 路径 | 学生可见（core） | 教师与教务另见（campus） |
| --- | --- | --- | --- |
| 01 今日 | `#/today` | 总览、随堂测、闪卡、专注、语音 | — |
| 02 计划 | `#/plan` | 备考方案、排期、目标与资料、学科包 | — |
| 03 练习与复盘 | `#/practice` | 错题本、周报、苏格拉底导师 | — |
| 04 诊断与决策 | `#/diagnosis` | 驾驶舱、学情洞察、漏洞地图 | — |
| 05 协作与关怀 | `#/collab` | 心理自评、恢复站 | 班级看板、教师工作台、班级报表、教务对接、学科包审核、家长报告 |
| 06 设置 | `#/settings` | 账号与安全 | — |

首页改为编辑式版面：倒计时大字、教练引文、任务清单（含「为什么是它」依据展开）、薄弱点排行与节奏事实表；顶栏只保留目标切换与联网状态。

账号安全不依赖邮件与短信：忘记密码时用**密保问题**或**一次性恢复码**（`#/recover`，三步完成），验证通过后签发 10 分钟一次性票据再重设密码；重设成功后该账号所有设备下线。`设置 → 登录设备` 可查看每台设备的浏览器/系统、IP 与最后活跃时间，支持单台下线与「退出其他设备」。JWT 带 `jti`，撤销会话后旧 token 立即失效，而不是只清浏览器缓存。既未设置密保也未保存恢复码的账号，可由运营执行 `python backend/scripts/reset_password.py <用户名>` 兜底。

三条主链路都走 SSE：今日首页「教练一句话」（P07）、苏格拉底导师「流式讲解」（P06）、语音教练提问（P15）。协议统一为 `stage → delta → result/fallback`：先返回规则计算阶段，再由模型流式生成，**通过统一信封校验后才展示**；模型不可用时显示规则文案并标注原因。

出题质量：英语科目（四级 / 六级 / 雅思 / 托福等）强制英文题干与选项，并拦截「属于哪个模块」「最符合…理解方式」这类元问题；两次输出不合格时回退规则题并如实标注。

事件总线（文档 7.5）把 `quiz_answered`、`task_overdue`、`fatigue_high`、`phase_changed`、`risk_detected`、`material_uploaded` 路由到对应处理器链，并写入 `events` 表；`#/diagnosis?tab=evidence` 与 `/api/events/routes` 可直接展示「事件 → 决策」。

## v2.0 提示词工程与调用审计

v2.0 文档第六章的提示词工程体系已落地为可运行代码，而不是散落在各服务里的字符串：

- **提示词库**：`backend/app/prompts/library.py` 收录 P00–P18 共 19 条提示词（与附录 E 逐字一致），每条带档位、`temperature`、`max_tokens`、超时、输入变量、兜底策略与输出契约；
- **五层拼装**：`build_messages()` = P00 前缀 + 任务 system + `<output_contract>`（system）+ 渲染后的动态数据（user）；变量缺失直接报错，不静默发送空提示词；
- **统一信封**：`parse_json_strict()` 去 Markdown 围栏容错解析，`check_envelope()` 校验 `{data, evidence_refs, confidence, warnings}`；
- **版本注册**：启动时把 19 条提示词幂等写入 `prompt_versions`，正文哈希变化即记录；`GET /api/prompts/versions` 可查；
- **调用审计**：网关按档位路由（`LLM_TIER_FAST/GENERAL/REASONING`），每次真实调用写 `llm_calls`（prompt@version、模型、档位、token、延迟、缓存、校验与兜底标记），`GET /api/llm-calls` 汇总成功率与兜底率；
- **LSV 快照**：`build_lsv()` 把快照写进 `lsv_snapshots` 并保留 sha256，证据链引用同一个 `snapshot_id`；
- **前端**：提示词正文与契约页面已按需求移除，调用审计（`GET /api/llm-calls`）并入系统接入页；
- **评测用例**：启动时把 19 条提示词各生成一条 `eval_cases` 常规用例（可通过 `/api/prompts/{id}/cases` 查询）；
- **自检**：`cd backend && python -m app.prompts.library` 校验 19 条提示词可渲染、示例信封合法。

> 数据表已从 33 张扩展到 41 张：新增 `review_cards`、`task_variants`、`events`、`eval_cases`、`safety_events`，加上 `llm_calls`、`prompt_versions`、`lsv_snapshots`，附录 B 的 8 张新表全部具备真实写入点。

> 仍未落地的部分（独立事件总线进程、云产品真实接通、PDF/Word 导出页眉页脚）已在
> [docs/v2.0落地补全记录-2026-11-11.md](docs/v2.0落地补全记录-2026-11-11.md) 中逐条如实标注，答辩时按“降级如实标注”的口径说明即可。

## 与赛题要求的对应

| 赛题要求 | 本项目做法 |
| --- | --- |
| 使用码道 CodeArts 开发 | 需求拆解、脚手架、接口、测试与部署脚本均由码道辅助完成，保留对话记录 |
| 基于已有智能体与 Skills | 使用码道工程规范，自建 4 个学习类 Skills 并放入 `skills/` |
| 开通并关联 RDS、Redis | `DATABASE_URL` 切 RDS，`REDIS_URL` 切 DCS；本地 SQLite / 内存缓存零配置可跑 |
| 云上快速部署 | 提供 Dockerfile、docker-compose 与一键启动脚本 |
| 入围后开源 | 仓库含 README、架构说明、部署文档与 License |

## License

MIT
