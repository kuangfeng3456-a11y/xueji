# 3. API 接口全景图

> 基于 `backend/app/api/` 下 35 个路由模块 + `main.py` 中 `/api/health` 端点的代码审计结果。  
> 所有路径均已拼接 `/api` 全局前缀与各模块自身 prefix。  
> **端点总数：120**（含 health），分布于 **36 个逻辑模块**。

---

## 3.1 端点总表

### 认证与数据隐私（auth · prefix=/auth）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/auth/register` | 注册，返回 JWT | ✗ | `create_access_token`, `hash_password` |
| POST | `/api/auth/login` | 登录，返回 JWT | ✗ | `verify_password`, `create_access_token` |
| GET | `/api/auth/me` | 当前用户信息 | ✓ | — |
| GET | `/api/auth/me/export` | 导出全部学习数据(JSON) | ✓ | 直接 DB 查询聚合 |
| DELETE | `/api/auth/me` | 删除账号及全部数据 | ✓ | 级联删除 7 张表 |

### 目标与资料（goals · prefix=/goals）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals` | 目标列表 | ✓ | DB 查询 |
| POST | `/api/goals` | 创建目标 | ✓ | DB insert |
| PUT | `/api/goals/{goal_id}` | 更新目标 | ✓ | DB update |
| DELETE | `/api/goals/{goal_id}` | 删除目标 | ✓ | 级联删除 KP/Mastery/Task |
| GET | `/api/goals/{goal_id}/knowledge-points` | 知识点树+掌握度 | ✓ | DB 查询聚合 |
| POST | `/api/goals/{goal_id}/knowledge-points` | 手动添加知识点 | ✓ | DB insert |
| DELETE | `/api/goals/{goal_id}/knowledge-points/{kp_id}` | 删除知识点 | ✓ | DB delete |
| POST | `/api/goals/{goal_id}/materials/text` | 文本导入+知识点抽取 | ✓ | `extract_knowledge_points`, `persist_points` |
| POST | `/api/goals/{goal_id}/materials/upload` | 文件上传+知识点抽取 | ✓ | `extract_text`, `scan_text`, `extract_knowledge_points`, `index_material` |
| GET | `/api/goals/{goal_id}/materials` | 资料列表 | ✓ | DB 查询 |

### 计划与任务（plan · prefix=/goals）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/goals/{goal_id}/plan` | 生成学习计划 | ✓ | `planner_generate` |
| GET | `/api/goals/{goal_id}/tasks` | 任务列表(可按日期筛选) | ✓ | DB 查询 |
| PATCH | `/api/goals/tasks/{task_id}` | 更新任务状态(打卡/跳过) | ✓ | `record_event`, cache invalidation |
| GET | `/api/goals/{goal_id}/tasks/{task_id}/why` | 任务价值解释(反事实) | ✓ | `task_why`, `retention`, `stability_for_stage` |
| POST | `/api/goals/{goal_id}/tasks/{task_id}/minutes` | 调整任务时长(弹性阶梯) | ✓ | `record_event`, cache invalidation |
| POST | `/api/goals/{goal_id}/auto-adjust` | 自动调整(顺延/补计划/冲刺) | ✓ | `auto_adjust_today` |
| POST | `/api/goals/{goal_id}/replan` | 手动触发重排 | ✓ | `replan` |
| GET | `/api/goals/{goal_id}/replan-logs` | 重排历史 | ✓ | DB 查询 |

### 错题、掌握度与周报（learning · prefix=/goals）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/goals/{goal_id}/mistakes/photo` | 上传错题图片 | ✓ | 文件保存, magic bytes 校验 |
| POST | `/api/goals/{goal_id}/mistakes` | 错题录入+AI归因+重排 | ✓ | `diagnose`, `apply_answer`, `replan`; **限流 30次/min** |
| GET | `/api/goals/{goal_id}/mistakes` | 错题列表(分页+分类筛选) | ✓ | DB 查询 |
| DELETE | `/api/goals/mistakes/{mistake_id}` | 删除错题 | ✓ | DB delete |
| POST | `/api/goals/{goal_id}/mastery/{kp_id}/answer` | 自测答对/答错 | ✓ | `apply_answer` |
| GET | `/api/goals/{goal_id}/mastery` | 掌握度列表+7日变化 | ✓ | DB 查询聚合 |
| POST | `/api/goals/{goal_id}/reports` | 生成周报 | ✓ | `reporter_generate` |
| GET | `/api/goals/{goal_id}/reports` | 周报列表 | ✓ | DB 查询 |
| GET | `/api/goals/{goal_id}/reports/latest` | 最新周报 | ✓ | DB 查询 |

### 首页与元信息（dashboard · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/dashboard` | 首页聚合数据 | ✓ | `auto_adjust_today`(⚠️含写操作), `coach_message`, `build_rhythm` |
| GET | `/api/goals/{goal_id}/rhythm` | 学习节奏画像 | ✓ | `build_rhythm` |
| GET | `/api/skills` | Skills 注册表 | ✗ | `list_skills` |
| GET | `/api/meta` | 运行环境信息 | ✗ | settings 读取 |

### 强制学习与摄像头（focus · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/focus/start` | 开始专注学习 | ✓ | DB insert FocusSession |
| GET | `/api/focus/active` | 查询进行中专注 | ✓ | DB 查询; ⚠️超时自动完成并打卡 |
| POST | `/api/focus/{session_id}/heartbeat` | 上报离开次数 | ✓ | 超3次记违约 `_record_violation` |
| POST | `/api/focus/{session_id}/snapshot` | 上传摄像头学习见证 | ✓ | 文件保存, magic bytes 校验, ≤5MB |
| POST | `/api/focus/{session_id}/finish` | 完成专注并打卡 | ✓ | DB update, task 状态变更 |
| POST | `/api/focus/{session_id}/abort` | 中止专注并记违约 | ✓ | `_record_violation` |
| GET | `/api/goals/{goal_id}/violations` | 违约记录列表 | ✓ | DB 查询 |
| GET | `/api/focus/history` | 最近专注记录 | ✓ | DB 查询 |

### 班级看板与学习搭子（social · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/classes` | 我的班级列表 | ✓ | DB 查询 |
| POST | `/api/classes` | 创建班级 | ✓ | DB insert + 生成邀请码 |
| POST | `/api/classes/join` | 邀请码加入班级 | ✓ | DB insert ClassMember |
| POST | `/api/classes/{class_id}/leave` | 退出班级 | ✓ | 创建者不可退出 |
| DELETE | `/api/classes/{class_id}` | 删除班级 | ✓ | **仅创建者**; 级联删除成员 |
| GET | `/api/classes/{class_id}/dashboard` | 班级看板 | ✓ | `build_class_dashboard`; 需成员身份 |
| DELETE | `/api/classes/{class_id}/members/{member_id}` | 移除成员 | ✓ | **仅创建者**; 不能移除自己 |
| GET | `/api/users/search` | 搜索同学 | ✓ | DB LIKE 查询, limit 10 |
| GET | `/api/buddies` | 学习搭子列表 | ✓ | `buddy_profiles` |
| POST | `/api/buddies` | 添加学习搭子 | ✓ | 双向 Buddy 记录 |
| DELETE | `/api/buddies/{buddy_id}` | 解除搭子关系 | ✓ | 双向删除 |

### 语音问答（coach · prefix=/coach）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/coach/ask` | 语音/文字问答 | ✓ | `answer_question` |

### 学科 Skill 包市场（skill_market · prefix=/skill-packages）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/skill-packages` | Skill 包列表 | ✓ | `package_views` |
| POST | `/api/skill-packages/{slug}/apply` | 一键导入知识点包 | ✓ | `apply_package` |

### 学情洞察与冲刺（insights · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/twin` | 学习数字孪生 | ✓ | `build_twin` |
| GET | `/api/goals/{goal_id}/twin/forecast` | 孪生预测 | ✓ | `build_twin_forecast` |
| GET | `/api/goals/{goal_id}/insights` | 学情洞察(热力图/雷达/徽章) | ✓ | `build_insights`, `ai_insight_report` |
| GET | `/api/goals/{goal_id}/forecast` | 冲刺预测 | ✓ | `build_forecast`, `ai_forecast_strategy` |
| POST | `/api/goals/{goal_id}/apply-forecast` | 应用推荐时长并重排 | ✓ | `replan`, `build_forecast`, `auto_adjust_today` |
| POST | `/api/goals/{goal_id}/rest` | 疲劳降载 | ✓ | 保留1任务, 其余顺延 |

### 闪卡与随堂测（study_tools · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/flashcards` | 闪卡队列 | ✓ | `build_deck` |
| GET | `/api/goals/{goal_id}/flashcards/{kp_id}/explain` | AI 释义+记忆技巧 | ✓ | `ai_flashcard_explanation` |
| POST | `/api/goals/{goal_id}/flashcards/{kp_id}/review` | 记得/忘记 | ✓ | `review_card` |
| POST | `/api/goals/{goal_id}/quiz/generate` | AI 出题 | ✓ | `generate_quiz` |
| POST | `/api/goals/{goal_id}/quiz/submit` | 判分+错因归因+错题入库 | ✓ | `grade_quiz` |

### AI 导师与资源工厂（tutor · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/goals/{goal_id}/socratic` | 苏格拉底式引导 | ✓ | `tutor.socratic_reply` |
| POST | `/api/goals/{goal_id}/socratic/recall` | 复述检查 | ✓ | `tutor.recall_check` |
| POST | `/api/goals/{goal_id}/resources/generate` | 学习资源生成 | ✓ | `tutor.generate_resources` |

### 教师决策台（teacher · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/classes/{class_id}/teacher-dashboard` | 教师教学决策台 | ✓ | `teacher_dashboard`; **仅班级创建者** |

### 接入状态（integrations · prefix=/integrations）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/integrations/cloud` | 华为云实例状态 | ✓ | `cloud_instances` |
| GET | `/api/integrations` | 接入状态总览 | ✓ | `describe_integrations` |
| POST | `/api/integrations/test` | 逐项真实探活 | ✓ | `test_integrations` |

### 学习驾驶舱（cockpit · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/cockpit` | 准备度/风险/关键任务 | ✓ | `compute_readiness`, `build_risks` |

### 知识漏洞地图（knowledge · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/knowledge-graph` | 知识依赖图+漏洞 | ✓ | `build_graph` |
| POST | `/api/gaps/{gap_id}/verify` | 生成漏洞验证题 | ✓ | `generate_quiz` |
| POST | `/api/gaps/{gap_id}/submit` | 验证判分+修复任务 | ✓ | `grade_quiz`, `record_evidence`; 通过→fixed, 失败→verified+插入修复任务 |

### 知识图谱（knowledge_graph · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/graph` | 显式知识图谱 | ✓ | `knowledge_graph.get_graph` |
| POST | `/api/goals/{goal_id}/graph/sync` | 同步图谱边关系 | ✓ | `knowledge_graph.sync_edges` |
| GET | `/api/goals/{goal_id}/graph/nodes/{kp_id}` | 节点详情+邻居 | ✓ | `knowledge_graph.node_detail` |

### 外部知识库（knowledge_base · prefix=/knowledge-base）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/knowledge-base/probe` | 外部知识源探活 | ✓ | `knowledge_base.probe` |
| GET | `/api/knowledge-base/lookup` | 术语查询 | ✓ | `knowledge_base.lookup` |

### 可信资料 RAG（rag · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/goals/{goal_id}/documents/search` | 资料检索 | ✓ | `rag.search`, `record_event` |
| POST | `/api/goals/{goal_id}/documents/reindex` | 重建索引 | ✓ | `rag.reindex_goal` |

### 未来模拟实验室（simulation · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/simulate` | 四策略模拟 | ✓ | `build_simulation`, `record_evidence` |

### 风险救援中心（risks · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/risks` | 五类备考风险 | ✓ | `build_risks` |
| POST | `/api/goals/{goal_id}/risks/{code}/resolve` | 确认风险救援 | ✓ | `resolve_risk`, `record_evidence` |

### 收益密度排程（schedule · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/schedule/preview` | 排程预览 | ✓ | `schedule_preview` |

### 策略实验室（experiments · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/experiments` | 实验列表 | ✓ | `list_experiments` |
| POST | `/api/goals/{goal_id}/experiments` | 创建策略实验 | ✓ | `start_experiment` |
| POST | `/api/experiments/{experiment_id}/finish` | 结束实验 | ✓ | `finish_experiment`; 归属校验 |
| GET | `/api/experiments/{experiment_id}/report` | 实验报告 | ✓ | `build_report`; 归属校验 |

### AI 探针与评审（ai_lab · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/probes` | 探针题列表 | ✓ | DB 查询 |
| POST | `/api/goals/{goal_id}/probes/generate` | AI 生成探针题 | ✓ | `generate_probes` |
| POST | `/api/probes/{probe_id}/submit` | 作答探针题 | ✓ | `submit_probe`; 归属校验 |
| POST | `/api/mistakes/{mistake_id}/trace` | 生成思维路径回放 | ✓ | `get_or_create_trace`; 归属校验 |
| GET | `/api/mistakes/{mistake_id}/trace` | 读取思维路径 | ✓ | DB 查询; 归属校验 |
| POST | `/api/goals/{goal_id}/panel/review` | 多智能体评审 | ✓ | `run_review` |
| GET | `/api/goals/{goal_id}/panel/reviews` | 评审历史 | ✓ | DB 查询 |
| POST | `/api/goals/{goal_id}/freshness/scan` | 资料时效扫描 | ✓ | `scan_freshness` |
| GET | `/api/goals/{goal_id}/freshness` | 时效报告 | ✓ | DB 查询聚合 |
| GET | `/api/goals/{goal_id}/freshness/history` | 时效扫描历史 | ✓ | DB 查询 |
| POST | `/api/goals/{goal_id}/panel/debate` | 多智能体辩论 | ✓ | `run_debate` |
| GET | `/api/goals/{goal_id}/panel/runs` | Agent 运行记录 | ✓ | `list_agent_runs` |

### P1 诊断增强（advanced · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/forecast/montecarlo` | 蒙特卡洛区间预测 | ✓ | `monte_carlo_forecast` |
| GET | `/api/goals/{goal_id}/phase` | 备考阶段状态机 | ✓ | `phase_for` |
| GET | `/api/goals/{goal_id}/fatigue` | 疲劳指数+认知负荷 | ✓ | `fatigue_index`, `cognitive_load` |

### 证据链与认知负荷（evidence · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/evidence` | 学习证据链 | ✓ | `list_evidence` |
| GET | `/api/goals/{goal_id}/cognitive-load` | 认知负荷评估 | ✓ | `compute_load` |
| POST | `/api/goals/{goal_id}/cognitive-load/apply` | 认知负荷调节 | ✓ | `apply_load` |

### 知识漏洞预警（risk_forecast · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/risk-forecast` | 漏洞风险预测 | ✓ | `risk_forecast.list_risks` |
| GET | `/api/goals/{goal_id}/risk-forecast/history` | 预测历史 | ✓ | `risk_forecast.risk_history` |
| POST | `/api/risk-forecast/{prediction_id}/verify` | 验证预测 | ✓ | `risk_forecast.apply_verification`; 归属校验 |
| POST | `/api/risk-forecast/{prediction_id}/feedback` | 预测反馈 | ✓ | `risk_forecast.submit_feedback`; 归属校验 |
| POST | `/api/risk-forecast/{prediction_id}/questions` | 生成验证题 | ✓ | `generate_probes`; 归属校验 |

### 学习事件与掌握度（learning_events · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/learning-events` | 学习事件流 | ✓ | `learning_events.list_events` |
| GET | `/api/goals/{goal_id}/learning-events/stats` | 事件统计 | ✓ | `learning_events.event_stats` |
| GET | `/api/goals/{goal_id}/mastery/{kp_id}/detail` | 掌握度明细 | ✓ | `learning_events.mastery_detail` |

### 学习者状态向量（lsv · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/lsv` | LSV 快照 | ✓ | `build_lsv` |

### 心理评估（psychology · prefix=/psychology）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/psychology/crisis-check` | 危机文本检测 | ✓ | `wellbeing_check` |
| GET | `/api/psychology/scales` | 量表列表 | ✓ | `psychology.scale_list` |
| GET | `/api/psychology/scales/{key}` | 量表详情 | ✓ | `psychology.get_scale` |
| POST | `/api/psychology/assess` | 提交测评 | ✓ | `psychology.assess`; DB insert |
| GET | `/api/psychology/history` | 测评历史 | ✓ | DB 查询 |

### 娱乐内容（entertainment · prefix=/entertainment）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/entertainment/kinds` | 内容类型列表 | ✓ | 常量读取 |
| GET | `/api/entertainment/{kind}` | 获取内容 | ✓ | `entertainment.fetch`; 缓存 300s |

### 模块大模型（module_ai · prefix=/module-ai）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/module-ai/list` | 模块列表 | ✓ | `module_ai.module_list` |
| POST | `/api/module-ai/{module}` | 调用模块 AI 能力 | ✓ | `module_ai.generate`; 缓存 1800s |

### 模型网关（model_gateway · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/model-gateway` | LLM 调用统计 | ✓ | `llm.stats` |

### AI 可靠性评测（eval_center · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| POST | `/api/eval/run` | 运行评测 | ✓ | `run_eval` |
| GET | `/api/eval/runs` | 评测历史 | ✓ | `list_runs` |
| POST | `/api/eval/synthetic-students` | 生成合成学生 | ✓ | `generate_students` |

### 家长授权报告（family · 无 prefix）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/goals/{goal_id}/consent` | 查询授权状态 | ✓ | `consent.get_consent` |
| POST | `/api/goals/{goal_id}/consent` | 设置授权 | ✓ | `consent.set_consent` |
| GET | `/api/goals/{goal_id}/parent-report` | 家长成长摘要 | ✓ | `consent.build_parent_report`; **需已授权** |

### 系统端点（main.py 直接注册）

| 方法 | 完整路径 | 用途 | 鉴权 | Service / 核心逻辑 |
|------|---------|------|------|-------------------|
| GET | `/api/health` | 健康检查 | ✗ | 返回 DB/Cache/LLM 状态 |

---

## 3.2 鉴权与权限模型

### 鉴权机制

项目使用单一鉴权依赖 `get_current_user`（定义于 `deps.py`）：
- 从 `Authorization: Bearer <JWT>` 提取 token
- `decode_token` 解析 payload，取 `sub` 字段作为 user_id
- 查库确认用户存在，否则 401
- 未携带 token → 401「请先登录」；token 无效/过期 → 401「登录状态已失效」

### 公开端点（无需鉴权）

仅 **5 个**端点不需要登录：

| 端点 | 说明 |
|------|------|
| `POST /api/auth/register` | 注册 |
| `POST /api/auth/login` | 登录 |
| `GET /api/skills` | Skills 注册表（只读元数据） |
| `GET /api/meta` | 运行环境信息 |
| `GET /api/health` | 健康检查 |

其余 **115 个**端点均需 Bearer Token。

### 归属校验（Ownership）

大部分涉及 `goal_id` 的端点通过 `get_user_goal(goal_id, user, db)` 进行归属校验：若 goal 不存在或 `goal.user_id != user.id`，返回 404。以下端点使用独立的归属校验逻辑：

| 端点 | 校验方式 |
|------|---------|
| `DELETE /api/classes/{class_id}` | `school_class.owner_id != user.id` → 403 |
| `DELETE /api/classes/{class_id}/members/{member_id}` | 同上 |
| `GET /api/classes/{class_id}/teacher-dashboard` | 同上 |
| `POST /api/classes/{class_id}/leave` | 创建者不可退出 → 400 |
| `GET /api/classes/{class_id}/dashboard` | 需 `_membership` 成员身份 → 403 |
| `POST /api/experiments/{experiment_id}/finish` | `experiment.user_id != user.id` → 404 |
| `GET /api/experiments/{experiment_id}/report` | 同上 |
| `POST /api/probes/{probe_id}/submit` | `probe.user_id != user.id` → 404 |
| `POST/GET /api/mistakes/{mistake_id}/trace` | `mistake.user_id != user.id` → 404 |
| `POST /api/risk-forecast/{prediction_id}/*` (3个) | `prediction.user_id != user.id` → ValueError |
| `GET /api/goals/{goal_id}/parent-report` | 需 `consent.granted == True` → 403 |

### 角色模型

项目**没有**独立的角色/RBAC 系统。权限完全通过归属关系隐式表达：
- 班级创建者（`owner_id`）拥有删除班级、移除成员的独占权限
- 教师决策台仅对班级创建者开放
- 家长报告需学生主动授权（consent 机制）

---

## 3.3 横切机制

### 统一异常处理

`main.py` 注册了两个全局异常处理器：

| 异常类型 | HTTP 状态码 | 响应体 |
|---------|-----------|--------|
| `SQLAlchemyError` | 503 | `{"detail": "数据库暂不可用...", "request_id": "..."}` |
| `Exception`（兜底） | 500 | `{"detail": "服务内部错误，已记录日志", "request_id": "..."}` |

各端点内部的业务异常通过 `HTTPException` 抛出，状态码包括 400/403/404/429/502。

### 中间件

| 中间件 | 功能 |
|--------|------|
| `CORSMiddleware` | 允许配置的 origins，credentials=true，methods/headers=* |
| `cache_control` | 静态资源长缓存(1年)，HTML/API 响应 no-store |
| `access_log` | 请求计时、X-Request-ID/X-Trace-Id 注入、结构化日志 |

### 限流

仅 **1 处**显式限流：
- `POST /api/goals/{goal_id}/mistakes`：`cache.incr("ratelimit:diagnose:{user_id}", ttl=60)`，上限 30 次/分钟，超限返回 429。

其余端点**无任何限流保护**，包括 AI 调用密集的探针生成、面板评审、苏格拉底对话等。

### 缓存

采用双层缓存架构：
1. **应用层 Cache**（`cache.py`）：支持 Redis / MemoryCache 回退，TTL 按场景设定（300s~86400s）
2. **LLM 语义缓存**（`llm.py`）：精确匹配 system+user+temperature+max_tokens，TTL 600s，上限 500 条

缓存使用场景：

| 场景 | TTL | 位置 |
|------|-----|------|
| Dashboard coach 消息 | 600s | `dashboard.py` |
| 娱乐内容 | 300s | `services/entertainment.py` |
| AI 内容生成(闪卡释义等) | 1800s | `services/ai_content.py` |
| 模块 AI 输出 | 1800s | `services/module_ai.py` |
| 心理评估解读 | 600s | `services/psychology.py` |
| 随堂测答案 | 至提交时删除 | `services/quiz.py` |
| 外部知识库探活 | 90s | `services/knowledge_base.py` |
| 集成测试 | 20s(内存) | `services/integrations.py` |

写操作后主动失效 dashboard 缓存：`cache.delete(f"dashboard:{user_id}:{goal_id}")`，覆盖 plan/learning/insights 等模块。

### 文件上传

3 个文件上传端点，均使用 `UploadFile = File(...)`：

| 端点 | 大小限制 | 格式校验 | 存储 |
|------|---------|---------|------|
| `POST .../mistakes/photo` | ≤5MB (`MAX_UPLOAD_BYTES`) | 后缀 + 无 magic bytes 校验 | `/uploads/{user_id}/{uuid}{ext}` |
| `POST .../focus/{id}/snapshot` | ≤5MB | 后缀 + magic bytes 校验 | `/uploads/{user_id}/focus_{sid}_{uuid}{ext}` |
| `POST .../materials/upload` | 无显式大小限制 | 后缀(由 `extract_text` 决定) | 内容存 DB Material 表 |

注意：`mistakes/photo` 缺少 magic bytes 校验，而 `focus/snapshot` 有完整的文件头验证。`materials/upload` 没有文件大小上限，存在 DoS 风险。

---

## 3.4 API 设计观察

### 3.4.1 GET 端点中的写操作（坏味道）

**`GET /api/dashboard`** 是最严重的设计问题。该端点在 `auto_adjust_today()` 中执行了以下写操作：
- 调用 `replan()` 重排任务（INSERT/UPDATE Task 表）
- 调用 `build_plan()` 生成新计划（INSERT Task 表）
- 调用 `db.commit()` 提交事务

这意味着每次前端刷新首页都会触发潜在的数据库写入。违反 REST 语义（GET 应幂等且安全），且导致：
- 浏览器预加载/爬虫可能意外修改数据
- 无法安全地做 HTTP 缓存
- 调试困难（GET 请求产生副作用）

**`GET /api/focus/active`** 同样存在类似问题：当检测到专注时间已耗尽时，自动将 session 标记为 completed 并将关联 task 标记为 done，包含 `db.commit()`。

### 3.4.2 路径命名不一致

| 问题 | 具体表现 |
|------|---------|
| **prefix 分裂** | goals/plan/learning 三个模块共享 `/goals` prefix，但各自独立注册；social/focus/insights 等无 prefix 却也在路径中使用 `/goals/{id}/...` |
| **资源路径不统一** | 同为 goal 子资源，有的走 `/goals/{id}/xxx`（如 flashcards），有的走顶层 `/gaps/{id}/xxx`（如 verify/submit）、`/probes/{id}/submit`、`/mistakes/{id}/trace`、`/experiments/{id}/finish` |
| **PATCH vs PUT** | 任务状态更新用 PATCH `/tasks/{task_id}`，目标更新用 PUT `/goals/{goal_id}`，但任务时长调整又用 POST `/{goal_id}/tasks/{task_id}/minutes` |
| **动词混入路径** | `/apply-forecast`、`/auto-adjust`、`/replan`、`/rest`、`/crisis-check` 等 RPC 风格端点混杂在 RESTful 资源路径中 |

### 3.4.3 重复/冗余端点

| 端点对 | 问题 |
|--------|------|
| `GET /api/goals/{id}/knowledge-graph` (knowledge.py) vs `GET /api/goals/{id}/graph` (knowledge_graph.py) | 两个不同模块提供知识图谱数据，前者返回 `KnowledgeGraphOut`（含漏洞），后者返回 `get_graph` 结果，职责边界模糊 |
| `GET /api/goals/{id}/forecast` (insights.py) vs `GET /api/goals/{id}/forecast/montecarlo` (advanced.py) vs `GET /api/goals/{id}/twin/forecast` (insights.py) | 三种预测端点，命名和返回结构各异，缺乏统一的预测 API 抽象 |
| `GET /api/goals/{id}/cognitive-load` (evidence.py) vs `GET /api/goals/{id}/fatigue` (advanced.py) | 两者都计算认知负荷，`fatigue` 端点内部调用了 `cognitive_load()` 函数，存在功能重叠 |

### 3.4.4 返回结构不统一

| 问题 | 示例 |
|------|------|
| 列表端点有的返回裸数组，有的包装在对象中 | `GET /goals` → `List[GoalOut]`；`GET /goals/{id}/experiments` → `{"experiments": [...]}`；`GET /goals/{id}/learning-events` → `{"events": [...]}` |
| 部分端点返回 dict 而非 response_model | `GET /api/goals/{id}/twin/forecast`、`GET /api/goals/{id}/phase`、`GET /api/goals/{id}/fatigue` 等均无 response_model |
| 错误响应格式不一致 | 业务异常用 `HTTPException(detail=str)`，但 `risk_forecast` 的三个端点用 `raise ValueError(...)` 而非 HTTPException，会被全局 handler 捕获为 500 而非预期的 404 |

### 3.4.5 分页缺失

绝大多数列表端点仅有 `limit` 参数，**没有 offset/cursor 分页**：
- `GET /goals/{id}/mistakes`：有 limit(默认20, max 100)，无 offset
- `GET /goals/{id}/reports`：无分页
- `GET /classes/{id}/dashboard`：无分页
- `GET /goals/{id}/panel/reviews`：limit 默认10
- `GET /psychology/history`：limit 默认10

唯一有较完整分页的是 `GET /goals/{id}/learning-events`（limit + event_type 筛选），但仍缺 offset。

### 3.4.6 其他设计问题

- **risk_forecast 端点的 ValueError**：`verify`、`feedback`、`questions` 三个端点在归属校验失败时抛出 `ValueError` 而非 `HTTPException`，导致返回 500 而非 404，且暴露内部异常信息。
- **`POST /api/eval/synthetic-students`** 不需要 DB 会话却要求鉴权，纯计算型端点可考虑公开或降级。
- **`GET /api/skills` 和 `GET /api/meta`** 是唯二公开的业务端点，但 `/meta` 暴露了 LLM 配置状态（`llm_enabled`、`llm_model`），在生产环境中可能泄露基础设施信息。

---

## 3.5 README 对账

README（第 222-285 行）列出了约 60 行 API 描述。与代码实际端点对比：

### 代码中存在但 README 未记录的端点（共 38 个）

| 模块 | 端点 | 说明 |
|------|------|------|
| auth | `GET /api/auth/me` | 当前用户信息 |
| goals | `PUT /api/goals/{id}` | 更新目标 |
| goals | `DELETE /api/goals/{id}` | 删除目标 |
| goals | `POST /api/goals/{id}/knowledge-points` | 手动添加知识点 |
| goals | `DELETE /api/goals/{id}/knowledge-points/{kp_id}` | 删除知识点 |
| goals | `GET /api/goals/{id}/materials` | 资料列表 |
| plan | `GET /api/goals/{id}/tasks/{task_id}/why` | 任务价值解释 |
| plan | `POST /api/goals/{id}/tasks/{task_id}/minutes` | 任务时长调整 |
| plan | `GET /api/goals/{id}/replan-logs` | 重排历史 |
| learning | `DELETE /api/goals/mistakes/{mistake_id}` | 删除错题 |
| learning | `GET /api/goals/{id}/mastery` | 掌握度列表 |
| learning | `GET /api/goals/{id}/reports/latest` | 最新周报 |
| focus | `POST /api/focus/{id}/abort` | 中止专注 |
| social | `POST /api/classes/{id}/leave` | 退出班级(README 提及但写法不准确) |
| knowledge_graph | `GET /api/goals/{id}/graph` | 显式知识图谱 |
| knowledge_graph | `POST /api/goals/{id}/graph/sync` | 同步图谱边 |
| knowledge_graph | `GET /api/goals/{id}/graph/nodes/{kp_id}` | 节点详情 |
| knowledge_base | `GET /api/knowledge-base/probe` | 外部知识源探活 |
| knowledge_base | `GET /api/knowledge-base/lookup` | 术语查询 |
| rag | `POST /api/goals/{id}/documents/search` | 资料检索 |
| rag | `POST /api/goals/{id}/documents/reindex` | 重建索引 |
| schedule | `GET /api/goals/{id}/schedule/preview` | 排程预览 |
| lsv | `GET /api/goals/{id}/lsv` | 学习者状态向量 |
| advanced | `GET /api/goals/{id}/forecast/montecarlo` | 蒙特卡洛预测 |
| advanced | `GET /api/goals/{id}/phase` | 备考阶段 |
| advanced | `GET /api/goals/{id}/fatigue` | 疲劳指数 |
| evidence | `GET /api/goals/{id}/evidence` | 证据链 |
| evidence | `GET /api/goals/{id}/cognitive-load` | 认知负荷 |
| evidence | `POST /api/goals/{id}/cognitive-load/apply` | 负荷调节 |
| risk_forecast | 全部 5 个端点 | 漏洞预警系列 |
| learning_events | 全部 3 个端点 | 学习事件流 |
| psychology | 全部 5 个端点 | 心理评估系列 |
| entertainment | 全部 2 个端点 | 娱乐内容 |
| module_ai | 全部 2 个端点 | 模块 AI |
| model_gateway | `GET /api/model-gateway` | 模型网关状态 |
| eval_center | 全部 3 个端点 | AI 评测 |
| family | 全部 3 个端点 | 家长授权 |
| teacher | `GET /api/classes/{id}/teacher-dashboard` | 教师决策台 |
| ai_lab | `POST /api/goals/{id}/panel/debate` | 多智能体辩论 |
| ai_lab | `GET /api/goals/{id}/panel/runs` | Agent 运行记录 |
| ai_lab | `GET /api/goals/{id}/freshness/history` | 时效扫描历史 |
| insights | `GET /api/goals/{id}/twin/forecast` | 孪生预测 |
| tutor | 全部 3 个端点 | 苏格拉底导师系列 |

### README 记录但代码中不存在的端点

**0 个**。README 中列出的所有端点在代码中均有对应实现。

### README 描述不准确的端点

| README 描述 | 实际情况 |
|------------|---------|
| `GET/PATCH /api/goals/{id}/tasks · /api/goals/tasks/{taskId}` | PATCH 路径实际为 `/api/goals/tasks/{task_id}`（无 goal_id 前缀），与 GET 路径模式不一致 |
| `POST/DELETE /api/classes/{id}/leave · /api/classes/{id}` | leave 是 POST 不是 DELETE；两个操作合并在同一行容易误读 |
| `GET/POST /api/goals/{id}/cognitive-load · /apply` | cognitive-load 是 GET，apply 是 POST，但 README 写法暗示两者都支持 GET+POST |

### 差异总结

- README 覆盖率约 **55%**（记录了 ~65 个端点中的描述，实际 120 个）
- 未记录端点集中在 v2.0 新增模块（advanced、evidence、risk_forecast、learning_events、psychology、entertainment、module_ai、eval_center、family、teacher、tutor、knowledge_graph、knowledge_base、rag、lsv）
- README 无错误记录（不存在虚构端点），但部分路径描述不够精确
