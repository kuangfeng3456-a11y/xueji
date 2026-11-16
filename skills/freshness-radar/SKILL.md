---
name: freshness-radar
agent: Reporter
version: 2.1.0
---

# freshness-radar

评估学习资料是否过时，避免用旧年份、旧考纲的资料备考。

## 输入

- 资料名称与内容摘录
- 当前年份与考试名称

## 输出

- 时效评分（0–100）
- 具体问题列表
- 补资料建议

## 规则

1. 识别资料中的年份；距当前年份越久分数越低。
2. 检查是否包含最新考纲 / 题型说明。
3. 内容过少或缺少近年真题会提示补充。
4. 大模型评估失败时使用年份与关键词规则兜底。
5. 扫描结果写入学习证据链。

## 实现位置

- `backend/app/services/freshness.py`
- `backend/app/api/ai_lab.py`
- 前端：`frontend/src/views/Freshness.vue`