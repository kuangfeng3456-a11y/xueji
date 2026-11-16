# 学迹 Skills 目录

本目录存放可复用的学习类 Skill 包。每个 Skill 由「智能体 + 确定性规则 + 可选提示词模板」组成，学科包可替换。

| Skill | 智能体 | 作用 |
| --- | --- | --- |
| `plan-builder` | Planner | 生成周计划与每日微任务 |
| `mistake-diagnosis` | Diagnoser | 错题归因与补救建议 |
| `daily-coach` | Coach | 当日提醒、鼓励与调整说明 |
| `weekly-review` | Reporter | 周报复盘与下周重点 |
| `learning-cockpit` | Cockpit | 准备度评分、风险聚合与今日关键任务 |
| `knowledge-gap` | Diagnoser | 先修依赖追溯、候选漏洞与验证题确认 |
| `strategy-simulation` | Simulator | 多策略方案、结果区间与负荷对比 |
| `risk-rescue` | Coach | 五类风险识别、救援动作与前后对比 |
| `strategy-experiment` | Reporter | 学习方式小实验与个人收益排行 |
| `learning-probe` | Diagnoser | AI 主动探针、迁移压力测试与反脆弱挑战 |
| `thought-replay` | Diagnoser | 错题思维步骤回放与错误定位 |
| `ai-panel` | Panel | 计划官 / 诊断官 / 风险官 / 教练联合评审 |
| `freshness-radar` | Reporter | 资料年份、考纲与内容时效评估 |
| `cognitive-load` | Coach | 认知负荷计算与难度动态调节 |
| `evidence-chain` | Auditor | AI 判断依据留痕与追溯 |

## 设计原则

1. **规则优先**：排程、掌握度、预测、风险评分全部由程序规则完成，保证可复现。
2. **大模型可插拔**：未配置 LLM 时自动使用规则模板；配置后用于语义理解、出题、验证与措辞润色，输出必须经过结构校验。
3. **学科可替换**：新增学科只需替换知识点树与提示词，不需要改动核心引擎。
4. **可解释**：每个决策都能说出依据（公式、数据、前后对比），并写入学习证据链。

## 学迹 2.0 与 AI 增强

- 决策层：`learning-cockpit`、`knowledge-gap`、`strategy-simulation`、`risk-rescue`、`strategy-experiment`。
- AI 增强：`learning-probe`、`thought-replay`、`ai-panel`、`freshness-radar`、`cognitive-load`、`evidence-chain`。

## 与后端实现的对应

- 注册表：`backend/app/agents/skills.py`（可通过 `GET /api/skills` 查看）
- Planner：`backend/app/services/planner.py`
- Diagnoser：`backend/app/agents/diagnoser.py` + `rules.classify_mistake`
- Coach：`backend/app/agents/coach.py`
- Reporter：`backend/app/services/reporting.py`
- Cockpit：`backend/app/services/readiness.py`
- Knowledge Gap：`backend/app/services/knowledge_map.py`
- Simulation：`backend/app/services/simulation.py`
- Risk Rescue：`backend/app/services/readiness.py`
- Strategy Experiment：`backend/app/services/experiments.py`
- Learning Probe：`backend/app/services/probes.py`
- Thought Replay：`backend/app/services/thought_trace.py`
- AI Panel：`backend/app/services/panel.py`
- Freshness Radar：`backend/app/services/freshness.py`
- Cognitive Load：`backend/app/services/cognitive_load.py`
- Evidence Chain：`backend/app/services/evidence.py`