---
name: strategy-experiment
agent: Reporter
version: 2.0.0
---

# strategy-experiment

用小规模学习实验比较精读、刷题、闪卡与 AI 讲解的个人收益，把「哪种方法适合我」变成可测量数据。

## 输入

- 学习方式（read / practice / flashcard / ai_tutor）
- 实验天数（建议 3 天）
- 实验前后平均掌握度
- 即时测试与延迟测试分数

## 输出

- 实验记录（运行中 / 已完成）
- 掌握度增益（post − pre）
- 个人策略收益排行

## 规则

1. 创建实验时记录实验前平均掌握度与起止日期。
2. 结束实验时记录当前平均掌握度、即时与延迟测试分数。
3. 收益 = 实验后掌握度 − 实验前掌握度；同一策略取多次实验平均值。
4. 延迟测试用于避免只被短期记忆误导。

## 实现位置

- `backend/app/services/experiments.py`
- `backend/app/api/experiments.py`
- 前端：`frontend/src/views/Experiments.vue`