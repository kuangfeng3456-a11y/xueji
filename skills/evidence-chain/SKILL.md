---
name: evidence-chain
agent: Auditor
version: 2.1.0
---

# evidence-chain

为每个 AI 判断记录输入数据、规则、输出与来源，支持现场逐条追溯。

## 输入

- 判断类型（探针、回放、评审、时效、风险、模拟、负荷）
- 主题、数据快照、输出、引擎（llm / rule）

## 输出

- 按时间排序的证据链
- 可展开的 JSON 依据
- 模型生成与规则生成的分布

## 规则

1. subject 最多 120 字、output 最多 2000 字、payload 最多 6000 字。
2. 所有 AI 决策模块在产生结论时写入证据。
3. 证据按用户与目标隔离。
4. 前端提供类型筛选与展开依据。

## 实现位置

- `backend/app/services/evidence.py`
- `backend/app/api/evidence.py`
- 前端：`frontend/src/views/EvidenceSpace.vue`