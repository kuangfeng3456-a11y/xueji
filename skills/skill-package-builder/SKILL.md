---
name: skill-package-builder
agent: Planner
version: 1.0.0
---

# skill-package-builder

把一个学科的模块与知识点树封装成可复用的 Skill 包，注册后可在「计划 → 学科包」里一键应用到任意考试目标。

## 输入

- 学科包名称、学科、标签、一句话简介
- 知识点树文本，每行一个模块，格式：`模块: 知识点(权重), 知识点(权重)`

示例：

```
听力: 短对话(1.4), 长对话(1.5), 听力篇章(1.6)
阅读: 选词填空(1.4), 仔细阅读(1.9)
写作: 议论文结构(1.4), 常用句型(1.3)
```

## 输出

- 注册后的 Skill 包（slug、名称、知识点数）
- 规范化后的知识点树（模块 → 子知识点 → 权重）
- 学科包市场里的模块入口：模块可点开查看知识点与掌握度，并直接出题或背单词

## 规则

1. 同名知识点只保留一条，重复自动去重。
2. 权重夹在 0.1–5.0 之间，缺省 1.0；未写权重按 1.2 处理。
3. 父节点未定义时，子知识点提升为顶级，保证知识点树始终可落地。
4. 至少需要一个知识点，否则返回 400。
5. 注册的包 `official=false`，与官方包同处市场列表，可应用到任意目标。

## 实现位置

- 接口：`POST /api/skill-packages`（`backend/app/api/skill_market.py`）
- 服务：`create_package()`（`backend/app/services/skill_packages.py`）
- 前端向导：`frontend/src/views/SkillMarket.vue`（四步：基本信息 → 知识点树 → 预览 → 注册并应用）

## 调用示例

```bash
curl -X POST http://127.0.0.1:8000/api/skill-packages \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"name":"考研英语冲刺包","subject":"英语","tags":["考研"],
       "points":[{"name":"阅读","parent":null,"weight":1.5},
                 {"name":"仔细阅读","parent":"阅读","weight":1.9}]}'
```
