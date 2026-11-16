---
name: learning-cockpit
agent: Cockpit
version: 2.0.0
---

# learning-cockpit

把「准备度」作为统一指标，聚合知识覆盖、时间负荷、验证漏洞、逾期任务与违约，回答「现在到底稳不稳」。

## 输入

- 高权重知识点掌握度
- 待完成任务总时长与今日任务
- 剩余天数、每日可用分钟
- 已验证漏洞数、逾期任务数、近 7 天违约次数
- 今日关键任务（按优先级）

## 输出

- 准备度分数（0–100）与等级（excellent / good / risk / critical）
- 知识覆盖度、时间负荷比
- 风险列表与今日关键任务
- 漏洞数、策略实验数

## 规则

1. 覆盖度 = Σ(权重 × 掌握度) / Σ权重
2. 负荷比 = 待完成分钟 / (剩余天数 × 每日可用分钟)
3. 准备度 = 覆盖度×100 − max(0, 负荷比−1)×25 − 漏洞×4 − 逾期×3 − 违约×2
4. 风险按知识 → 时间 → 执行 → 记忆 → 策略顺序生成，每条带原因与建议动作

## 实现位置

- `backend/app/services/readiness.py`
- `backend/app/api/cockpit.py`
- 前端：`frontend/src/views/Cockpit.vue`