---
name: reverse-grader
agent: Diagnoser
version: 1.0.0
---

# reverse-grader

AI 扮演「犯了典型错误的学生」交一份答卷，用户当老师指出错在哪一步、属于哪类错、该怎么改。

## 输入

- 知识点、错因（可选，留空按三类轮换）
- 用户选择：错误步骤、错因、修正说明

## 输出

- 待批改答卷（题干 + 3~5 个步骤，只有一处错）
- 三项得分：定位 45 / 错因 30 / 修正 25
- 真相对照：错误步骤原文、正确写法、必须提到的关键词、学生为什么这么错
- 辨别力画像：能发现哪类错 × 自己常犯哪类错

## 规则

1. 错误步骤、错因、正确写法、关键词**在出题时写死**，模型只出题不判分。
2. 位置：指对满分 45，指到相邻步骤 15 分。
3. 错因：必须说对（三类：概念不清 / 方法不会 / 粗心），说错 0 分。
4. 修正：按预置关键词覆盖率折算 25 分，缺哪个词明确告诉你。
5. 出题时不下发 error_step / correct_step，防止一眼看答案。
6. 同一份答卷只能批改一次。

## 实现位置

- 接口：`POST /api/teaching/reverse/start`、`POST /api/teaching/reverse/grade`、`GET /api/teaching/reverse/profile`
- 服务：`backend/app/services/reverse_teaching.py`
- 页面：练习与复盘 → 讲与判 → 我来判卷
