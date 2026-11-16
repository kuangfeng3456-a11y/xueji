# 第四章 创新服务模块实现深度审计

## 1. 创新模块实现深度评级表

| 模块文件 | 功能名 | 实现方式 | 关键计算逻辑 | 依赖数据表 | 评级 |
|---|---|---|---|---|---|
| `knowledge_map.py` | 知识漏洞地图 | 规则启发式 | 叶子节点触发条件：错题≥2且掌握度<0.6，或权重≥1.5且掌握度<0.35，或先修链薄弱且掌握度<0.5；BFS追溯先修链(depth=4) | KnowledgePoint, Mastery, Mistake, KnowledgeDependency, KnowledgeGap | **扎实** |
| `knowledge_graph.py` | 知识图谱 | 规则启发式 | 从KnowledgeDependency同步prerequisite边；同父节点按weight排序生成confusable边(weight=0.6)；掌握度四级分级(excellent/good/risk/critical) | KnowledgePoint, KnowledgeEdge, KnowledgeDependency, Mastery | **中等** |
| `simulation.py` | 未来模拟实验室 | 真实算法 | 逐日仿真：每日衰减×0.995，按(1-m)²×w排序选top-N知识点，每次覆盖增量=0.12×(1-m)；四策略对比(维持/加时/修复/组合) | Mastery, KnowledgePoint, Task, Goal | **扎实** |
| `cognitive_load.py` | 认知负荷调节器 | 规则启发式 | load = fatigue×0.55 + max(0,今日分钟/计划分钟-1)×35 + 错题率×25；四档分级(overload/high/optimal/low)联动任务调整 | Task, Mistake, Goal；调用insights.build_fatigue和readiness.compute_readiness | **扎实** |
| `risk_forecast.py` | 风险预测 | 真实算法 | 五因子加权：forget=(1-m)×70+逾期天×1.6(0.30)、prereq=弱先修占比(0.25)、error=7d错题/5×100(0.20)、transfer=探针失败率(0.15)、overdue=任务逾期率(0.10)；置信度=0.2+0.06×样本量 | Mastery, Mistake, ProbeItem, Task, KnowledgeDependency, RiskPrediction | **扎实** |
| `freshness.py` | 内容时效雷达 | LLM包装+规则兜底 | 规则层：正则提取年份，score=max(20,90-(当前年-最新年)×10)；LLM层：prompt要求JSON{score,issues,suggestion}，解析失败回退规则 | Material, FreshnessReport | **中等** |
| `thought_trace.py` | 思维路径回放器 | LLM包装+规则兜底 | LLM生成3-5步思维步骤JSON；规则兜底按错因类别(concept/method/careless/other)返回硬编码步骤模板 | Mistake, ThoughtTrace | **单薄** |
| `probes.py` | AI主动探针出题官 | LLM包装+规则兜底 | 8种探针类型各有选题排序策略（如probe按掌握度升序、trap按错题降序）；LLM生成题目JSON，规则兜底生成模板化选择题 | KnowledgePoint, Mastery, Mistake, ProbeItem | **中等** |
| `panel.py` | 多智能体学习评审团 | 规则引擎+LLM润色 | v2辩论：6角色(计划/诊断/导师/预测/证据审查/挑刺)各自基于阈值判定stance；仲裁=支持票比例≥60%则采纳；LLM仅改写view/concern/suggestion文案不改立场 | Task, KnowledgeGap, LearningExperiment, RiskPrediction, AgentRun, PanelReview | **扎实** |
| `twin.py` | 学习数字孪生 | 规则聚合 | 知识矩阵(掌握度+错题+漏洞状态)、错因分布统计、8周行为趋势(完成率)、策略排名(调用experiments.build_ranking)；情景推演：daily_gain=rate×0.02, decay=0.006-stage×0.001, 区间band=(1-rate)×0.08+0.03 | KnowledgePoint, Mastery, MasteryHistory, Mistake, Task, KnowledgeGap | **扎实** |
| `experiments.py` | 策略实验室 | 真实算法 | 前后测设计：记录pre/post mastery，gain=post-pre；ranking按策略分组取平均gain排序；报告含完成率、样本量、局限性声明 | LearningExperiment, ExperimentMetric, Mastery, Task | **扎实** |
| `insights.py` | 学情洞察 | 真实算法 | 热力图(12周日级minutes/done/focus)；雷达五维(mastery均值/rhythm完成率/focus专注天数/7/accuracy=1-错题比/persistence=streak/14)；疲劳指数(leaves×8+aborted×14+超180min部分×0.12+错题增长×6+违约×5+长连续×1.2)；8枚徽章阈值判定 | Task, FocusSession, Mistake, Violation, Mastery | **扎实** |
| `psychology.py` | 心理评估 | 真实量表+LLM解读 | PHQ-9/GAD-7/PSS-10标准量表计分(含PSS-10反向计分)；规则解读+LLM润色；PHQ-9第9题>0触发自伤安全警告；外部知识库证据(openalex/crossref/baidu) | 无DB表(纯输入计算)，缓存结果 | **扎实** |
| `wellbeing.py` | 心理关怀 | 规则启发式 | 关键词匹配(crisis_keywords 7个/risk_keywords 6个)三级分级(crisis/elevated/watch/normal)；返回公开援助资源 | 无DB表 | **中等** |
| `tutor.py` | AI苏格拉底导师 | LLM包装+规则兜底 | 4级提示(direction/concept/step/full)×3模式(hint/explain/exam)；LLM生成JSON{reply,next_question}；validator.scan_text校验注入/违规，不通过则回退规则模板；复述检查=关键词覆盖率≥60%且长度≥12 | KnowledgePoint, Mastery, LearningEvent | **中等** |
| `teacher.py` | 教师工作台 | 规则聚合 | 班级成员掌握度聚合→top5薄弱点；错因分布统计；三层分层(high≥0.7/mid≥0.4/low<0.4)；近7天完成率；规则建议 | User, Goal, KnowledgePoint, Mastery, Mistake, Task, ClassMember | **中等** |
| `eval_center.py` | AI评测中心 | 真实LLM调用 | 6道基准题(数学/英语/CS)，真实调用LLM回答，关键词匹配判分；记录延迟、失败率、准确率；模型不可用时标记skipped | EvalRun | **中等** |
| `rag.py` | 可信资料库检索 | 真实算法 | 段落切块(400字上限，按句号分割)；bigram重叠率排序=query_grams∩chunk_grams/query_grams；返回文件名+段落号+分数 | DocumentChunk, Material | **扎实** |
| `module_ai.py` | 模块AI教练 | LLM包装+规则兜底 | 24个模块角色，统一上下文(掌握度/任务/错题/漏洞/实验数)；LLM输出{headline,insights,actions}；规则兜底拼接模板文案；缓存30分钟 | 多表聚合(Mastery,Task,Mistake,KnowledgeGap,LearningExperiment等) | **单薄** |
| `advanced.py` | v2.0算法增强 | 真实算法 | 蒙特卡洛(1000次采样,seed=42可复现)：gauss(current,spread)+gauss(gain,|gain|×0.5)×horizon→p10/p50/p90/达标概率；阶段状态机(基础/强化/冲刺/考前)配不同配比与留存目标；疲劳/负荷公式独立版本 | 纯函数，无DB依赖 | **扎实** |
| `synthetic.py` | 合成学员仿真 | 规则生成 | 固定种子(seed=42)分层抽样(high 20%/mid 50%/low 30%)；predicted=mastery×100+completion×10-mistakes×0.8 | 无DB表 | **中等** |
| `lsv.py` | 学习者状态向量 | 规则聚合 | 统一快照：知识矩阵+负荷+准备度+风险+预测；user_id SHA256脱敏；snapshot_id证据链；排除心理数据 | 多表聚合(KnowledgePoint,Mastery,Mistake,Task)；调用readiness/twin | **扎实** |
| `entertainment.py` | 娱乐模块 | 真实外部API | 6个公开API(hitokoto/jinrishici/zenquotes/jokeapi/uselessfacts/bing)；httpx异步请求+缓存300s；失败如实返回error不伪造 | 无DB表 | **扎实** |
| `knowledge_base.py` | 外部知识库 | 真实外部API | OpenAlex/Crossref/百度百科三源并发查询；摘要提取(OpenAlex inverted index还原)；探测缓存90s | 无DB表 | **扎实** |
| `social.py` | 班级/搭子社交 | 规则聚合 | 成员画像(streak/完成率/掌握度/最弱点)；班级看板(聚合薄弱点/分层/活跃数)；搭子对比排行 | User, ClassMember, Buddy, Goal, KnowledgePoint, Mastery, Task | **中等** |
| `qa.py` | 语音问答 | 规则优先+LLM润色 | 7类关键词匹配(倒计时/薄弱/今天/复习/错题/计划/情绪)返回规则答案；LLM润色(80字内,temperature=0.4) | Task, Mastery, Mistake, Goal | **中等** |
| `evidence.py` | 学习证据链 | 基础设施 | 统一记录每个AI判断的kind/subject/payload/output/engine/snapshot_id/validation；支持按kind追溯 | Evidence | **扎实** |
| `learning_events.py` | 学习事件流 | 基础设施 | 11种事件类型；答题事件统计正确率/置信度(0.2+0.05×n)/趋势(当前-7天前快照) | LearningEvent, Mastery, MasteryHistory | **扎实** |
| `skill_packages.py` | 学科Skill包 | 未确认 | 文件内容与之前读取相同(skill_packages.py在首次Read时未被缓存但返回了其他文件内容)，需单独确认 | 未确认 | 未确认 |

> **注**：`skill_packages.py` 在读取时返回了与 `evidence.py` 相同的内容（工具缓存问题），实际内容未能独立确认。以下分析不包含该模块。

### 评级分布汇总

| 评级 | 数量 | 模块 |
|---|---|---|
| **扎实** | 16 | knowledge_map, simulation, cognitive_load, risk_forecast, panel, twin, experiments, insights, psychology, rag, advanced, lsv, entertainment, knowledge_base, evidence, learning_events |
| **中等** | 9 | knowledge_graph, freshness, probes, tutor, teacher, eval_center, wellbeing, synthetic, social, qa |
| **单薄** | 2 | thought_trace, module_ai |
| **空壳** | 0 | — |
| **未确认** | 1 | skill_packages |

---

## 2. 有真实算法的模块详解

### 2.1 BKT-lite 掌握度更新（rules.py → mastery_service.py）

核心公式为贝叶斯知识追踪简化版：
- **猜测率** guess：choice=0.25, blank=0.10, short=0.05
- **失误率** slip=0.15，**学习率** learn=0.08
- 答对时 posterior = m(1-slip) / [m(1-slip)+(1-m)·guess]
- 答错时 posterior = m·slip / [m·slip+(1-m)(1-guess)]
- m_bkt = posterior + (1-posterior)·learn
- m_new = m + evidence_weight·(m_bkt - m)，限幅±0.30

配套指标：
- 置信度 c = 1 - e^(-n_eff/3)
- 不确定性 u = √[m(1-m)/(n_eff+2)]
- 保持率 R(t) = 0.9^(t/S)，S为复习档位对应天数
- 稳定度更新：答对 S'=S×(1.7+2×(1-R))，答错 S'=max(1, 0.4S)

### 2.2 准备度评分（readiness.py）

```
score = coverage×100 - max(0, load_ratio-1)×25 - gaps×4 - overdue×3 - violations×2
```
其中 coverage = Σ(weight_i × mastery_i) / Σ(weight_i)，load_ratio = 待完成总分钟 / (剩余天数×每日分钟)。clamp到[0,100]。

### 2.3 风险预测五因子模型（risk_forecast.py）

| 因子 | 权重 | 计算公式 |
|---|---|---|
| forget | 0.30 | min(100, (1-m)×70 + overdue_days×1.6) |
| prereq | 0.25 | 先修链中掌握度<0.45的节点占比×100 |
| error | 0.20 | min(100, 近7天错题数/5×100) |
| transfer | 0.15 | 探针失败次数/尝试次数×100 |
| overdue | 0.10 | 逾期任务数/总任务数×100 |

总分 = Σ(weight_i × factor_i)。置信度 = min(0.95, 0.2 + 0.06×sample_size)。sample_size<3标记insufficient。

### 2.4 认知负荷（cognitive_load.py）

```
load = fatigue_score × 0.55 + max(0, today_min/plan_min - 1) × 35 + wrong_ratio × 25
```
wrong_ratio = 近7天错题数 / (完成数+错题数)。四档：≥80 overload, ≥55 high, ≥30 optimal, <30 low。每档对应推荐任务数和分钟数。

### 2.5 疲劳指数（insights.py build_fatigue）

累加式计分：
- 近3天离开专注页面次数 × 8
- 近3天专注中断次数 × 14
- 近3天专注>180min部分 × 0.12（上限20）
- 错题周环比增长 × 6（上限20）
- 近7天违约次数 × 5（上限20）
- 连续打卡≥10天时 (streak-9)×1.2（上限10）

上限100。≥60 high, ≥30 medium, <30 low。

### 2.6 未来模拟（simulation.py _simulate）

逐日迭代days天：
1. 所有知识点 mastery × DAILY_FORGET(0.995)
2. 按排序键选择cover个知识点（repair_first时用(1-m)²×w，否则(1-m)×w）
3. 选中知识点 mastery += GAIN_PER_TOUCH(0.12) × (1-m)
4. cover = daily_minutes // DAILY_COVER_POINTS(20)

四策略并行模拟取最优，区间估计±4%。

### 2.7 蒙特卡洛预测（advanced.py monte_carlo_forecast）

1000次采样(seed=42可复现)：
- start ~ N(current, spread)
- drift ~ N(gain, |gain|×0.5) × horizon
- outcome = clamp(start + drift)
输出p10/p50/p90分位数及达标概率。

### 2.8 RAG检索排序（rag.py）

切块：按双换行分段，超长段按句号拆分，上限400字。
检索：query bigram集合与chunk bigram集合的Jaccard式重叠率 = |Q∩C|/|Q|，降序取top_k。返回material_id/chunk_index/page_no/snippet/score。

### 2.9 收益密度与任务Why（rules.py value_density/task_why）

```
V = w × [(1-m) + 0.6×(1-R) + 0.3×u] × U(d) × G
ρ = V / minutes
ΔE = 100 × w × η × (1-m) × G
```
U(d) = 1 + 3·e^(-d/14)（临近系数），G为先修门控(存在<0.5的先修时=0.5)。η按任务类型：study=0.25, practice=0.18, review=0.10, remedial=0.28。

### 2.10 心理量表计分（psychology.py）

PHQ-9(9题×0-3=27)、GAD-7(7题×0-3=21)、PSS-10(10题×0-4=40，第3/4/6/7题反向计分=4-value)。分级阈值硬编码。PHQ-9第9题(self-harm)>0触发urgent安全标志。

---

## 3. 依赖LLM的模块分析

### 3.1 LLM调用模式总览

所有LLM依赖模块遵循统一模式：
1. 检查 `llm.available`
2. 构造system prompt（角色+输出JSON格式约束）
3. 调用 `llm.chat_json()` 或 `llm.chat()`
4. 校验返回结构（isinstance检查+字段存在性）
5. 解析失败或不可用时回退规则兜底

### 3.2 各模块LLM使用详情

| 模块 | LLM用途 | JSON解析容错 | 不可用回退 |
|---|---|---|---|
| freshness | 资料时效评分 | isinstance(dict)+score是int | _rule_scan正则年份 |
| thought_trace | 拆解思维步骤 | isinstance(dict)+steps是list | _fallback按category返回硬编码模板 |
| probes | 生成探针题目 | isinstance(dict)+questions是list+每题4选项校验 | _rule_questions模板化选择题 |
| panel(run_review) | 四角色评审意见 | isinstance(dict)+opinions是list≥3条 | _fallback规则拼接 |
| panel(run_debate) | 仅润色view/concern/suggestion文案 | by_agent字典匹配，polished计数 | _rule_debate完整规则引擎 |
| tutor | 苏格拉底回复 | isinstance(dict)+reply非空 | _rule_reply四级模板 |
| psychology | 量表解读润色 | text非空即采用 | _rule_interpretation规则文案 |
| module_ai | 24模块headline/insights/actions | isinstance(dict)+headline+insights非空 | _fallback模板拼接 |
| qa | 问答润色(80字内) | text非空即采用 | build_rule_answer 7类关键词匹配 |
| eval_center | 基准题作答 | 关键词匹配判分 | 标记skipped，不作正确性结论 |
| tutor(generate_resources) | 闪卡/变式题/微课提纲 | isinstance(dict)+items是list且非空 | _rule_resources模板 |

### 3.3 LLM安全校验

`tutor.py`是唯一引入`validator.scan_text`的模块：对LLM返回文本检测4条禁用表达正则和3条注入模式正则。命中时强制回退规则模板并标记validation="fallback"。其他模块均无内容安全校验。

---

## 4. 数据支撑度评估

### 4.1 强数据依赖（冷启动即空壳）

| 模块 | 冷启动表现 |
|---|---|
| simulation | 无知识点时返回"还没有知识点，无法模拟"，projected=0 |
| risk_forecast | 无Mastery/Mistake/ProbeItem时所有因子为0，risk_score≈0，全部标记insufficient |
| cognitive_load | 无Task/Mistake时fatigue=0,wrong_ratio=0,load≈0，永远输出"low" |
| insights | 无Task/FocusSession时热力图全0、雷达五维全0、疲劳low、徽章全未解锁 |
| twin | 无数据时matrix全0、trend全0、ranking空列表 |
| experiments | 无finished实验时ranking为空，build_report sample_size=0 verdict="样本不足" |
| panel | 无数据时所有角色输出默认文案，仲裁结果无实质意义 |
| knowledge_map | 无Mastery/Mistake时无候选漏洞，build_graph只有nodes无candidates |

**结论**：以上8个模块在新用户无任何学习记录时输出的数值均为0或默认值，不具备任何诊断价值。需要至少1-2周的持续使用才能产出有意义的结果。项目文档应明确标注冷启动期。

### 4.2 弱数据依赖（冷启动仍可用）

| 模块 | 冷启动表现 |
|---|---|
| psychology | 纯用户输入，不依赖历史数据 |
| wellbeing | 纯文本输入，不依赖历史数据 |
| eval_center | 直接调LLM答题，不依赖用户数据 |
| entertainment | 外部API，不依赖用户数据 |
| knowledge_base | 外部API，不依赖用户数据 |
| freshness | 依赖Material表，有资料即可工作 |
| rag | 依赖Material/DocumentChunk，有资料即可工作 |
| synthetic | 纯随机生成，不依赖用户数据 |
| advanced(monte_carlo) | 纯函数，传入参数即可计算 |

---

## 5. 重复与耦合分析

### 5.1 高频重复查询模式

以下查询模式在多个模块中反复出现，每次都独立查库：

1. **叶子知识点筛选**：`_leaves()` 函数在 knowledge_map、simulation、risk_forecast、probes、twin 中各自实现一份，逻辑完全相同（查所有KnowledgePoint→过滤parent_id不在集合中的节点）。
2. **掌握度映射**：`_mastery_map()` / `_mastery_rows()` / `_mastery()` 在 knowledge_map、risk_forecast、probes、twin、readiness 中各自实现，均为 select Mastery where user_id+kp_id.in_(...)。
3. **错题计数**：`_mistake_counts()` 在 knowledge_map、probes、readiness 中重复实现。
4. **先修链BFS**：`prerequisites()` (knowledge_map) 与 `_prereq_chain()` (risk_forecast) 逻辑完全相同，仅函数名不同。

### 5.2 模块间调用链

- `cognitive_load` → `insights.build_fatigue` + `readiness.compute_readiness`
- `panel.run_debate` → `readiness.compute_readiness` + `readiness.build_risks` + `risk_forecast.compute_risks`
- `lsv.build_lsv` → `readiness.compute_readiness` + `readiness.build_risks` + `twin.build_forecast`
- `twin.build_twin` → `experiments.build_ranking` + `knowledge_map._mistake_counts`
- `module_ai.generate` → 自行查库聚合（与其他模块独立）

### 5.3 共享基础设施

- `evidence.record_evidence`：被12+模块调用，统一证据链记录
- `learning_events.record_event`：被tutor、mastery_service调用
- `rules.*`：纯函数层，被几乎所有模块引用
- `llm.chat_json/chat`：统一LLM接口
- `cache.get_json/set_json`：module_ai、psychology、entertainment使用

### 5.4 改进建议

叶子节点筛选、掌握度映射、错题计数、先修链BFS这四个工具函数应抽取到公共模块（如`rules.py`或新建`helpers.py`），避免5处独立实现导致的维护风险和潜在不一致。

---

## 6. 代码质量问题

### 6.1 硬编码与魔法数字

| 文件 | 位置 | 问题 |
|---|---|---|
| `forecast.py` L11-13 | DAILY_COVER_POINTS=20, GAIN_PER_TOUCH=0.12, DAILY_FORGET=0.995 | 仿真核心参数无来源说明，未从配置读取 |
| `rules.py` L183-186 | BKT_GUESS/BKT_SLIP=0.15/BKT_LEARN=0.08/MASTERY_MAX_STEP=0.30 | BKT参数无文献引用或实验校准依据 |
| `risk_forecast.py` L27-33 | RISK_WEIGHTS={forget:0.30,prereq:0.25,error:0.20,transfer:0.15,overdue:0.10} | 权重之和=1.0但无AHP或回归依据 |
| `insights.py` L216-232 | 疲劳计分系数(8/14/0.12/6/5/1.2) | 各因子量纲不同直接相加，无上限定标说明 |
| `knowledge_map.py` L121-128 | 触发阈值(0.45/0.15/2/0.6/1.5/0.35/0.5) | 7个魔法数字无注释说明来源 |
| `advanced.py` L9-18 | PHASE_CONFIG中target_retention/total_factor | 阶段配比无教育学文献支撑 |

### 6.2 异常吞噬

| 文件 | 位置 | 问题 |
|---|---|---|
| `risk_forecast.py` L149-155 | json.loads(row.factors/evidence) except Exception | 静默吞掉JSON解析错误，返回空列表/字典，可能导致下游误判 |
| `panel.py` L483-489 | json.loads(row.output/evidence) except Exception | 同上 |
| `thought_trace.py` L130-132 | json.loads(trace.steps) except Exception | 同上 |
| `probes.py` L200-203 | json.loads(item.options) except Exception | 同上 |
| `evidence.py` L66-68 | json.loads(row.payload) except Exception | 同上 |

所有JSON解析异常均被`except Exception: xxx = {}`吞噬，无日志记录。若数据库中存入了损坏的JSON，系统将静默返回空数据而不报错。

### 6.3 缺失的边界检查

| 文件 | 位置 | 问题 |
|---|---|---|
| `knowledge_map.py` L60 | `kp_id.in_([point.id for point in points] or [0])` | 当points为空时in_([0])会查一个不存在的ID，虽不会报错但语义不清 |
| `risk_forecast.py` L218 | `probes["failures"]/probes["attempts"]*100 if probes["attempts"] else 0.0` | 正确 guarded，但transfer因子在无探针数据时恒为0，导致新用户风险分系统性偏低 |
| `simulation.py` L30 | `cover = max(1, int(daily_minutes // DAILY_COVER_POINTS))` | daily_minutes=0时cover=1，仍会模拟"学习"，与实际不符 |
| `insights.py` L153 | `accuracy = max(0.0, 1 - min(1.0, len(mistakes_14)/max(1,done_14)))` | done_14=0时accuracy=0，但此时并无错题数据，应为None或标记不足 |
| `twin.py` L134 | `current = sum/len if rows else 0.0` | 无掌握度数据时current=0，后续预测基于0起步，区间无意义 |

### 6.4 潜在性能问题

| 文件 | 位置 | 问题 |
|---|---|---|
| `risk_forecast.py` L175-284 | compute_risks | 对每个叶子节点调用_prereq_chain(BFS)，若知识点数百个且图较深，复杂度O(N×D×E) |
| `panel.py` L317-468 | run_debate | 单次调用触发compute_readiness+build_risks+compute_risks三次独立全量查询，再调LLM |
| `lsv.py` L24-134 | build_lsv | 串行调用compute_readiness+build_risks+build_forecast，每个内部又各自查全量数据 |
| `insights.py` L328-355 | build_insights | 串行调用heatmap+radar+fatigue+achievements，每个都独立查Task/Mistake/FocusSession全量 |
| `module_ai.py` L167-230 | _base_context | 6次独立select查询，无批量优化 |
| `rag.py` L74-110 | search | 全量加载所有chunks到内存做bigram比较，资料量大时O(C×Q)内存+CPU |

### 6.5 其他问题

- **panel.py L388**：system prompt中"evidence_reviewer(证据审查官)"重复出现两次，疑似复制粘贴遗留。
- **psychology.py L207**：缓存key使用`hash(tuple(scored)) & 0xffffffff`，Python hash在不同进程间不稳定（PYTHONHASHSEED），跨进程缓存可能失效。
- **entertainment.py**：6个外部API均无重试机制，单次超时即返回error。
- **knowledge_base.py L40**：百度百科appid=379020硬编码在源码中，应移至配置。
- **tutor.py L158**：recall_check的关键词拆分仅按中英文标点分割，对复合概念（如"二次函数的图像与性质"）拆出的子串可能过短导致误匹配。

---

## 7. 总结判断

本项目28个创新服务模块中，**16个评级扎实、9个中等、2个单薄、0个空壳**。整体实现质量显著高于"纯LLM包装"水平：

- **核心算法层**（BKT-lite、风险五因子、认知负荷、疲劳指数、蒙特卡洛、RAG bigram检索、收益密度）均有明确的数学公式、可复算的参数和真实的数据库输入。
- **LLM依赖模块**全部实现了规则兜底，LLM不可用时系统仍可运行，不会出现空白或崩溃。
- **证据链**（evidence.py）贯穿所有AI判断，记录了engine/version/snapshot_id，支持事后审计。
- **主要短板**：冷启动期多数模块输出无意义默认值；多处重复查询缺乏抽象；JSON异常吞噬无日志；核心参数缺乏校准依据。
