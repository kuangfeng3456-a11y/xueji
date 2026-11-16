---
name: strategy-simulation
agent: Simulator
version: 2.0.0
---

# strategy-simulation

比较多种学习策略在剩余时间内的结果区间、每日负荷与风险等级，帮助用户先看见结果再决定投入。

## 输入

- 知识点掌握度与权重
- 剩余天数、每日可用分钟
- 当前待完成任务负荷

## 输出

- 四种方案：维持现状、增加时间、优先修复漏洞、修复+加时
- 每方案预计掌握度、区间（±4 个百分点）、负荷比、风险等级
- 推荐方案与不确定性说明

## 规则

1. 每天可覆盖知识点数 = 每日分钟 / 20（至少 1 个）。
2. 每次覆盖向 1.0 靠近 12%；未复习每天衰减 0.5%。
3. 修复优先方案按 (1−掌握度)² × 权重 排序，更偏向薄弱与高权重。
4. 展示区间与假设，不把预测当作成绩保证。

## 实现位置

- `backend/app/services/simulation.py`
- `backend/app/api/simulation.py`
- 前端：`frontend/src/views/Sprint.vue`