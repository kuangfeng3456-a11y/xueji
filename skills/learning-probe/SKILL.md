---
name: learning-probe
agent: Diagnoser
version: 2.1.0
---

# learning-probe

AI 主动寻找隐藏知识盲区，并提供迁移压力测试与反脆弱挑战两类训练。

## 输入

- 知识点掌握度、错题数、权重
- 目标考试与剩余时间

## 输出

- 主动探针题（probe）
- 迁移压力测试题（transfer）
- 反脆弱挑战题（challenge）
- 作答结果、掌握度变化与韧性值

## 规则

1. 探针：优先掌握度低且错题多的知识点。
2. 迁移：优先掌握度 0.3–0.75 的知识点，题目必须换情境或换问法。
3. 挑战：优先高权重知识点，故意加入陌生条件；答错不扣掌握度，只记录韧性。
4. 每题 4 个选项，答案由服务端保存，作答后写入证据链。

## 实现位置

- `backend/app/services/probes.py`
- `backend/app/api/ai_lab.py`
- 前端：`frontend/src/views/AiLab.vue`