---
name: thought-replay
agent: Diagnoser
version: 2.1.0
---

# thought-replay

把一道错题拆成 3–5 个思维步骤，指出错误发生在哪一步、为什么，而不只是给正确答案。

## 输入

- 题目、学生答案、正确答案
- 错因类别与补救建议

## 输出

- 思维步骤列表（thought / verdict / issue）
- 出错步骤序号
- 一句话总结

## 规则

1. 步骤覆盖审题、方法选择、执行、检查四个环节。
2. 四类错因有固定回退模板：概念不清 → 第 1 步；方法不会 → 第 2 步；粗心 → 检查步；时间不够 → 审题步。
3. 大模型输出必须包含步骤列表且出错步骤在范围内，否则回退模板。
4. 生成结果写入学习证据链。

## 实现位置

- `backend/app/services/thought_trace.py`
- `backend/app/api/ai_lab.py`
- 前端：错题页「回放思维路径」弹窗