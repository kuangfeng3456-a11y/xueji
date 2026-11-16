# 01 规则内核：架构与实现说明

## 1. 模块清单表

| 文件 | 核心职责 | 对外主要函数 | 被谁调用 |
|------|---------|-------------|---------|
| `rules.py` | 纯函数规则引擎：掌握度更新、复习间隔、优先级、错因分类、BKT-lite、收益密度、遗忘曲线 | `update_mastery`, `bkt_update`, `next_review_date`, `task_priority`, `urgency_coefficient`, `value_density`, `classify_mistake`, `retention`, `task_tiers`, `gate_for_prerequisites`, `expected_gain`, `task_why` | planner, mastery_service, flashcards, schedule_preview, readiness, reporting, quiz |
| `planner.py` | 计划生成（`build_plan`）与动态重排（`replan`）：按收益密度排序选任务、逾期顺延、错题补救插入、时长溢出推迟 | `build_plan`, `replan`, `task_to_dict` | auto_schedule, quiz, API routes |
| `auto_schedule.py` | 每次进入首页自动检查：无任务→生成、逾期→重排、临考≤7天→冲刺复习 | `auto_adjust_today` | API routes (首页) |
| `schedule_preview.py` | v1 优先级 vs v2 收益密度对比预览，展示先修门控影响 | `schedule_preview` | API routes |
| `mastery_service.py` | 掌握度 CRUD：初始化、答题后 BKT 更新、复习日期推进、历史快照、置信度/不确定性记录 | `apply_answer`, `ensure_mastery`, `ensure_goal_mastery`, `record_history`, `touch_history_for_today` | planner, quiz, flashcards, knowledge, reporting |
| `reporting.py` | 周报生成：完成率、掌握度变化、错题分布、薄弱点；可选 LLM 润色点评 | `build_weekly_report`, `generate_weekly_report` | API routes |
| `rhythm.py` | 学习节奏画像：常学时段、拖延规律、完成率 → 自适应每日任务数 | `build_rhythm` | planner (`build_plan`) |
| `flashcards.py` | 闪卡组构建与复习：按遗忘曲线排序到期卡片，记得/忘记触发掌握度更新 | `build_deck`, `review_card` | API routes |
| `quiz.py` | AI 随堂测：LLM 或规则出题 → 判分 → 错因归因 → 掌握度更新 → 触发重排 | `generate_quiz`, `grade_quiz` | API routes |
| `readiness.py` | 准备度评分（加权覆盖度 − 负荷 − 漏洞 − 逾期 − 违约）、风险识别与救援 | `compute_readiness`, `build_risks`, `resolve_risk` | API routes |
| `forecast.py` | 冲刺预测：逐日模拟遗忘+学习增益，反推达标所需每日时长 | `build_forecast` | API routes |
| `knowledge.py` | 知识点持久化：去重写入知识树并初始化掌握度 | `persist_points` | materials, API routes |
| `materials.py` | 资料解析：提取文本（txt/md/csv/docx/pdf）→ LLM 或规则抽取知识点树 | `extract_text`, `parse_knowledge_lines`, `extract_knowledge_points` | API routes |

## 2. 核心算法与公式

### 2.1 README 声称 vs 代码实际对照

| 规则 | README 描述 | 代码实际实现 | 一致性 |
|------|-----------|------------|--------|
| 掌握度更新 | `m_new = m_old + 0.3 × (r − m_old)` | **v1** `update_mastery()` 完全一致；**v2** `bkt_update()` 已升级为 BKT-lite 贝叶斯修正 + 学习转移 + 证据加权 + 防抖 | ⚠️ **部分不一致**：README 只描述了 v1 公式，代码中 `apply_answer()` 实际调用的是 v2 的 `bkt_update()`，v1 函数保留但未在主流程使用 |
| 复习间隔 | `1/2/4/7/15` 天，答错回到 1 天 | `REVIEW_INTERVALS = [1, 2, 4, 7, 15]`，答对 stage+1（上限 4），答错 stage=0 | ✅ 一致 |
| 任务优先级 | `权重 × (1 − 掌握度) × 临近系数` | `task_priority()` 实现一致，但有额外保护：`weight = max(weight, 0.1)`，`max(1-mastery, 0.05)` 防止零值 | ✅ 基本一致（有安全下限） |
| 临近系数 | `1 + 3 × e^(−剩余天数/14)` | `urgency_coefficient()`: `1 + 3 * math.exp(-max(days_left, 0) / 14)` | ✅ 一致 |
| 错题补救 | 同知识点 7 天内错题 ≥2 道插入 20 分钟补救任务 | `_analyze_mistakes()` 查 7 天内 Mistake 表，`len(items) >= 2` 触发；`REMEDIAL_MINUTES = 20`；最多取前 2 个知识点 | ✅ 一致 |

### 2.2 v2.0 新增算法（README 未提及）

以下算法存在于 `rules.py` 的 v2.0 区块，README 未描述：

| 算法 | 公式 | 常量 | 位置 |
|------|------|------|------|
| BKT-lite 更新 | 贝叶斯后验 + 学习转移：`posterior = P(M\|obs)`；`m_bkt = posterior + (1-posterior) × BKT_LEARN`；`m_new = old + ew × (m_bkt - old)`；防抖 ±0.30 | `BKT_GUESS={"choice":0.25,"blank":0.10,"short":0.05}`, `BKT_SLIP=0.15`, `BKT_LEARN=0.08`, `MASTERY_MAX_STEP=0.30` | `rules.py:190-209` |
| 置信度 | `c = 1 - e^(-n_eff / 3)` | 分母常数 3 | `rules.py:212-214` |
| 不确定性 | `u = sqrt(m(1-m) / (n_eff + 2))` | Laplace 平滑 +2 | `rules.py:217-220` |
| 保持率（遗忘曲线） | `R(t) = 0.9^(t/S)` | 底数 0.9 | `rules.py:229-231` |
| 稳定度更新 | 答对：`S' = S × (1.7 + 2×(1-R))`；答错：`S' = max(1, 0.4×S)` | 增长因子 1.7+2(1-R)，回退 0.4 | `rules.py:241-246` |
| 收益密度 | `V = w·[(1-m)+0.6·(1-R)+0.3·u]·U(d)·G`；`ρ = V/min` | `λ_forget=0.6`, `λ_uncertainty=0.3` | `rules.py:265-290` |
| 期望增益 | `ΔE = 100·w·η·(1-m)·G` | `GAIN_ETA={"study":0.25,"practice":0.18,"review":0.10,"remedial":0.28,"mock":0.12}` | `rules.py:293-296` |
| 先修门控 | 任一先修掌握度 < 0.5 → G=0.5，否则 G=1.0 | 阈值 0.5 | `rules.py:257-262` |
| 任务弹性阶梯 | standard / lite(50%) / minimal(≤5min) | — | `rules.py:249-254` |

### 2.3 其他关键规则

| 规则 | 公式/逻辑 | 位置 |
|------|----------|------|
| 准备度评分 | `score = coverage×100 - max(0,load_ratio-1)×25 - gaps×4 - overdue×3 - violations×2`，clamp [0,100] | `readiness.py:87-94` |
| 节奏自适应 | 近 28 天完成率 < 50% 且样本 ≥6 → 每日任务从 3 降为 2；平均延迟 ≥2 天且样本 ≥3 → 同样降为 2 | `rhythm.py:124-128` |
| 冲刺预测模拟 | 每日遗忘 `×0.995`，学习增益 `+0.12×(1-m)`，每天覆盖 `daily_minutes//20` 个知识点 | `forecast.py:12-13, _simulate()` |
| 错因分类 | 规则链：空答/时间关键词→time；相似度≥0.75→careless；题干含方法词→method；用户答含"不会"→concept；选择题相似度<0.3→concept；兜底→method | `rules.py:103-154` |
| 扰动度 | `D = 被移动任务数 / 未来7天任务总数`；D ≤ 0.3 为安全，超出需用户确认 | `planner.py:529-535` |
| 复习时长分配 | 第一个任务为 review 时占 `max(10, daily_minutes×0.3)`，其余均分剩余 | `planner.py:226-229` |

## 3. 数据流

### 3.1 计划生成（`build_plan`）

```
入口: planner.build_plan(db, user_id, goal, days=7)
  ├─ ensure_goal_mastery()          → 写 Mastery 表（补全缺失记录）
  ├─ _kp_map()                      → 读 KnowledgePoint 表
  ├─ _mastery_map()                 → 读 Mastery 表
  ├─ LearningEvent GROUP BY         → 读 LearningEvent 表（答题计数）
  ├─ KnowledgeDependency            → 读依赖关系表
  ├─ build_rhythm()                 → 读 Task 表（近28天行为统计）→ 决定 tasks_per_day
  ├─ FOR EACH day IN horizon:
  │   ├─ 对每个叶子知识点计算 value_density（含 retention、uncertainty、gate）
  │   ├─ 按 density/(1+planned_load) 排序选 top-N
  │   ├─ 优先选到期复习项
  │   └─ distribute_minutes() 分配时长
  └─ 批量 INSERT Task 表 → flush
输出: {tasks[], summary, days, total_minutes}
```

**读写表汇总**：读 KnowledgePoint、Mastery、LearningEvent、KnowledgeDependency、Task；写 Mastery（补全）、Task（新建）。

### 3.2 动态重排（`replan`）

```
入口: planner.replan(db, user_id, goal, trigger)
  ├─ 读 Task 表（未来7天计数、逾期任务）
  ├─ 逾期任务 → 修改 day=today，追加 reason
  ├─ _analyze_mistakes()           → 读 Mistake 表（7天内按 kp_id 分组）
  │   └─ ≥2 道 → INSERT remedial Task（20min, priority+0.5）
  ├─ 距考试≤7天且今日无review → INSERT review Task（15min）
  ├─ FOR EACH day IN 8天窗口:
  │   ├─ 读当日 pending Tasks
  │   ├─ 按 priority 排序
  │   └─ 累计时长超 daily_minutes → 向后找空位推迟或标记 skipped
  ├─ INSERT ReplanLog（changes JSON）
  └─ commit
输出: {trigger, changes[], disturbance, tasks[]}
```

**日志/证据**：每次重排写入 `ReplanLog` 表，包含完整 changes JSON 和 trigger 来源（manual/auto_overdue/auto_sprint/quiz/risk_rest/risk_knowledge）。

## 4. 规则兜底逻辑（无 LLM Key）

所有模块遵循统一降级模式：**LLM 仅负责语义/表达，核心计算全部由规则完成**。

| 模块 | LLM 用途 | 无 LLM 时行为 |
|------|---------|--------------|
| `quiz.py` | 生成题目内容 | `_rule_questions()` 自动生成归类选择题（"X属于哪个模块？"），题目质量较低但功能完整 |
| `materials.py` | 从资料抽取结构化知识点 | `parse_knowledge_lines()` 按 Markdown 标题/列表/章节正则解析，无结构文本按行拆分 |
| `reporting.py` | 润色教练点评（120字） | `_rule_content()` 模板拼接完整周报，缺少个性化点评但数据准确 |
| `planner.py` | 不参与 | 完全规则驱动，无 LLM 依赖 |
| `auto_schedule.py` | 不参与 | 完全规则驱动 |
| `flashcards.py` | 不参与 | 完全规则驱动 |
| `readiness.py` | 不参与 | 完全规则驱动 |
| `forecast.py` | 不参与 | 完全规则驱动 |
| `rhythm.py` | 不参与 | 完全规则驱动 |

LLM 模块自身有熔断机制：连续失败 ≥ `LLM_FAILURE_THRESHOLD` 次后进入冷却期（`LLM_COOLDOWN_SECONDS`），期间 `available` 返回 False，自动走规则路径。另有精确匹配缓存（TTL 可配）减少重复调用。

## 5. 代码质量观察

### 5.1 重复逻辑

| 问题 | 位置 | 说明 |
|------|------|------|
| `_goal_points` / `_leaf_points` 重复定义 | `flashcards.py:14`, `quiz.py:18`, `planner.py:58`, `risk_forecast.py:47` | 四处独立实现了相同的"过滤父节点取叶子"逻辑，应抽取到公共模块 |
| `_mastery_map` 类似查询 | `planner.py:44`, `readiness.py:24`, `schedule_preview.py:37` | 多处重复 Mastery 批量查询+字典构建 |
| 掌握度兜底 0.0 | 多处 `record.value if record else 0.0` | 模式正确但分散，可封装为 `get_mastery_value()` |

### 5.2 硬编码常量

| 常量 | 值 | 位置 | 建议 |
|------|---|------|------|
| `TASKS_PER_DAY` | 3 | `planner.py:40` | 已在 rhythm 中可自适应，但 replan 冲刺复习固定 15 分钟未参数化 |
| `REMEDIAL_MINUTES` | 20 | `planner.py:41` | 合理但应从配置读取 |
| `DAILY_COVER_POINTS` | 20 | `forecast.py:12` | 模拟精度依赖此值，未文档化 |
| `GAIN_PER_TOUCH` | 0.12 | `forecast.py:13` | 与 BKT_LEARN=0.08 不一致，两套学习增益参数 |
| `DAILY_FORGET` | 0.995 | `forecast.py:14` | 与遗忘曲线 `0.9^(t/S)` 是不同模型，forecast 用简化版 |
| 冲刺复习固定 15 分钟 | — | `planner.py:428` | 硬编码，不随 daily_minutes 缩放 |
| 风险救援 priority=3.5 / 3.0 | — | `readiness.py:316,351` | 魔法数字，应与 task_priority 体系对齐 |

### 5.3 潜在 Bug

| 问题 | 位置 | 说明 |
|------|------|------|
| `replan` 中 N+1 查询 | `planner.py:464-474` | 时长溢出推迟时，对每一天都执行一次 `select(Task).where(day==target)` 查占用时长，最坏 8×N 次查询 |
| `replan` 冲刺段 N+1 | `planner.py:411-413` | 排序 candidates 时对每个叶子节点单独查 Mastery，应批量查询 |
| `apply_answer` 额外查询 | `mastery_service.py:68-74` | 每次答题都 COUNT(LearningEvent) 获取 n_eff，高频答题时性能差 |
| `reporting.py` 循环查 Mastery | `reporting.py:89-91` | 对每个知识点单独查 Mastery 和 MasteryHistory，知识点多时严重 N+1 |
| `readiness.py` 循环查 Mastery | `readiness.py:26-31` | `_mastery_points` 已批量查，但 `build_risks` 中又调 `_mistake_counts` 可能重复 |
| `quiz.py` grade 后全量 replan | `quiz.py:228` | 只要有错题就触发完整 replan，包括 8 天窗口的时长平衡，代价较高 |
| `forecast._simulate` 复杂度 | `forecast.py:16-42` | O(days × n_points)，600 分钟上限 × 365 天 × 大量知识点时可能慢 |
| `datetime.utcnow()` 弃用 | `mastery_service.py:79` | Python 3.12+ 已弃用 utcnow()，应改用 datetime.now(timezone.utc) |

### 5.4 异常处理缺失

| 位置 | 问题 |
|------|------|
| `planner.py:build_plan` | 无 try-except，DB 异常直接抛出，前端收到 500 |
| `mastery_service.py:apply_answer` | `denominator` 在 `bkt_update` 中有 `>1e-9` 保护，但 `apply_answer` 本身无事务回滚保护 |
| `quiz.py:_llm_questions` | LLM 返回非法 JSON 时静默降级到规则出题（正确），但未记录降级日志 |
| `materials.py:extract_text` | docx/pdf 导入失败抛 ValueError，缺少结构化错误码 |
| `readiness.py:resolve_risk` | `code="memory"` 分支中 `ordered` 可能为空，`for point in ordered` 后的 `changes` 列表推导引用了未绑定的 `point` 变量（若 ordered 为空则 changes 为空列表，不会报错但逻辑不完整） |

### 5.5 架构亮点

- **纯函数与 IO 分离**：`rules.py` 全部为纯函数，零数据库依赖，可独立单元测试和答辩演示。
- **双版本共存**：v1 优先级和 v2 收益密度并行保留，`schedule_preview` 可直接对比两版排序差异。
- **证据链完整**：每次答题记录 LearningEvent（含 engine 版本号、置信度、不确定性）；每次重排记录 ReplanLog（含完整 changes JSON）。
- **熔断降级**：LLM 连续失败自动熔断 + 精确缓存，保证无 Key 时全功能可用。
- **扰动度控制**：replan 输出 disturbance 指标，D>0.3 标记为需用户确认，防止自动重排过度干扰。
