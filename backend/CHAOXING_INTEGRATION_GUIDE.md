# 第三方查题题库集成指南（柠檬题库 / LIKE知识库）

## 概述

本项目接入与以下两个参考同源的第三方**查题**题库接口：

- 仓库：https://github.com/destoryD/chaoxing-api （LIKE知识库 · datam.site）
- 文档：https://docs.lemtk.xyz/get-started.html （柠檬题库）

**接口形态（重要）**：这类接口是「按题干 + 选项查答案」，**不支持按知识点枚举题目**。
因此它用于对已有题目判答案 / 核验，不参与「按知识点自动出题」的题源链；
出题链仍由 内置题库 → 通用外部出题接口 → LLM → 规则兜底 承担。

## 接口一览

| 接口 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| 普通查询 | `POST /api/v1/cx` | Token 可选（免费、限流） | 题目未变形时命中率足够 |
| 高级查询 | `POST /api/v1/mcx` | Token 必填 | 题目变形时命中率更高 |
| 余额查询 | `GET /api/v1/balance?email=&token=` | Token + 邮箱 | 查询剩余调用点数（非实时） |

对接域名（CDN 在港/日/新，国内访问慢时切换备用域名）：

- `https://api.lemtk.xyz`
- `https://api.vanse.top`（备用）

### 请求与响应

普通 / 高级查询 POST Body：

```json
{
  "v": "1.0",
  "question": "题干内容",
  "type": "0",
  "options": "选项A|选项B|选项C|选项D"
}
```

题型代码：`0` 单选 / `1` 多选 / `2` 填空 / `3` 判断 / `4` 简答。

成功响应：

```json
{
  "code": 1000,
  "msg": "success",
  "data": { "answer": "热水#含水稀醇#热乙醇" }
}
```

常见返回码：`1000` 成功 / `1003` 暂无答案 / `1009` 无效 Token。

## 配置

编辑根目录 `.env`（或 `.env.example` 复制后修改）：

```env
# 题库域名
QBANK_BASE_URL=https://api.lemtk.xyz
# 备用域名: https://api.vanse.top

# Token：高级查询 mcx 必填；普通 cx 留空走免费限流通道
QBANK_TOKEN=

# 注册邮箱，仅余额查询接口使用
QBANK_EMAIL=

# 查询模式: cx=普通查询, mcx=高级查询
QBANK_MODE=cx
QBANK_TIMEOUT=8
```

向后兼容：未设置 `QBANK_*` 时，适配器会回落读取旧变量
`QUESTION_BANK_API_URL` / `QUESTION_BANK_API_KEY` / `QUESTION_BANK_TIMEOUT`。

## 后端集成点

### 1. 适配器

`backend/app/services/qbank_chaoxing.py`

- `lookup(question, question_type, options)`：按题干 + 选项查答案，返回
  `status / answer_texts / answer_indexes / latency_ms / detail`。
- `check_balance()`：查询余额，返回 `balance / banned / email`。
- `search(...)`：兼容旧调用链的占位方法，返回 `lookup_only` 状态与空列表。

### 2. 手动查题端点

`POST /api/goals/{goal_id}/quiz/search-chaoxing`

```bash
curl -X POST http://127.0.0.1:8000/api/goals/1/quiz/search-chaoxing \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <登录态Token>" \
  -d '{
    "question": "设函数 f(x)=x²，则 f(x) 在 x=1 处的导数为",
    "options": ["0", "1", "2", "3"],
    "question_type": "single_choice"
  }'
```

响应：

```json
{
  "status": "ok",
  "metadata": {
    "status": "ok",
    "latency_ms": 234,
    "detail": "命中 1 项答案",
    "answer_texts": ["2"],
    "answer_indexes": [2],
    "mode": "cx",
    "platform": "chaoxing"
  }
}
```

### 3. 余额查询端点

`GET /api/goals/{goal_id}/question-banks/balance`

返回余额、封禁标记与注册邮箱；**不下发 Token**。

## 配置与测试脚本

`backend/setup_external_qbank.py`：

```bash
cd backend

# 检查当前配置
python setup_external_qbank.py --check

# 余额查询（需 QBANK_TOKEN 与 QBANK_EMAIL）
python setup_external_qbank.py --balance

# 完整自测：配置展示 + 余额 + 样例题查题
python setup_external_qbank.py --test-chaoxing

# 交互式写入配置
python setup_external_qbank.py --configure
```

## 故障排查

| 状态 | 原因 | 处理 |
|------|------|------|
| `not_configured` | 未配置域名 / Token / 邮箱 | 检查 `.env` 中 `QBANK_BASE_URL`、`QBANK_TOKEN`、`QBANK_EMAIL` |
| `token_required` | `QBANK_MODE=mcx` 但未填 Token | 改为 `cx`，或填写 `QBANK_TOKEN` |
| `no_answer` (1003) | 题库未命中该题 | 换用 `mcx` 高级查询；核对题干与选项原文 |
| `invalid_token` (1009) | Token 无效或过期 | 到题库平台重新获取 Token |
| `timeout` | 网络慢 / CDN 不可达 | 增大 `QBANK_TIMEOUT`；切换备用域名 `api.vanse.top` |

## 与出题链的关系

```
出题请求
  → 内置题库
  → 通用外部出题接口（QUESTION_BANK_API_URL，按知识点返回题目）
  → LLM 模型补题
  → 规则题库兜底
```

查题题库（本指南）不在上述出题链中；它负责「拿到题目后核验答案」。

## ZERO 网课题库（第二家查题供应商）

项目同时内置了 ZERO 网课题库适配器（`backend/app/services/qbank_gomooc.py`），
接口形态与柠檬题库完全不同：

```
GET /api.php?token=<token>&question=<题干>
```

- 只有题干一个业务参数，没有题型 / 选项 / 平台参数；
- **必须带 Token**，没有免 token 通道，缺 token 返回 `code 1002`；
- 一个 Token 绑定调用额度，额度用尽返回 `code 429`（剩余次数: 0），需到 gomooc 侧充值；
- 不提供余额查询接口，`check_balance` 如实返回 `not_supported`。

配置（`.env`）：

```bash
QBANK_PROVIDER=gomooc
QBANK_GOMOOC_BASE_URL=https://api.gomooc.net   # 备用同源 https://api2.gomooc.net
QBANK_GOMOOC_ENDPOINT=/api.php
QBANK_GOMOOC_TOKEN=<你的 token>
QBANK_GOMOOC_MERGE_OPTIONS=true                 # 首轮未命中时把选项拼进题干再查
```

测试：

```bash
cd backend
python setup_external_qbank.py --check      # 查看当前供应商与配置
python setup_external_qbank.py --test-zero  # 真实查题
```

## 供应商与降级

`QBANK_PROVIDER`（`lemtk` / `gomooc`）选主供应商，`QBANK_FALLBACK_PROVIDER` 配备用供应商。
主供应商返回 `token_required` / `invalid_token` / `quota_exhausted` / `no_answer` / `timeout`
等状态时，`ChainedQBankAdapter` 会自动换下一家，返回的 metadata 带：

| 字段 | 含义 |
|------|------|
| `provider` | 这次答案实际来自哪家 |
| `path` | 尝试路径，如 `gomooc → lemtk` |
| `primary_status` / `primary_detail` | 主供应商为什么没答上 |

两家都失败时返回主供应商的原始状态，不会伪造成功。

