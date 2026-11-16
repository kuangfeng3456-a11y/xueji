---
name: knowledge-gap
agent: Diagnoser
version: 2.0.0
---

# knowledge-gap

从错题与低掌握知识点出发，沿先修依赖向上追溯，先列为候选漏洞，再用验证题确认，避免补错地方。

## 输入

- 知识点树与依赖关系
- 各知识点掌握度、错题数、权重
- 先修链

## 输出

- 知识依赖图（节点、边、状态）
- 候选漏洞（candidate）与已验证漏洞（verified）
- 验证题（DeepSeek 生成，失败用规则题）
- 修复任务（验证失败时自动插入）

## 规则

1. 依赖：父知识点 → 子知识点；同模块按顺序建立链式依赖。
2. 候选触发：错题 ≥2 且掌握度 <0.6；或高权重（≥1.5）且掌握度 <0.35；或先修链存在更薄弱环节且掌握度 <0.5。
3. 验证：生成 2 道题；全对 → fixed（排除）；有错 → verified（确认）并生成 20 分钟修复任务。
4. 每个知识点只保留一条漏洞记录，避免重复插入。

## 实现位置

- `backend/app/services/knowledge_map.py`
- `backend/app/api/knowledge.py`
- 前端：`frontend/src/views/KnowledgeMap.vue`