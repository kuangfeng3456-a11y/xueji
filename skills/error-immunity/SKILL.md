---
name: error-immunity
agent: Diagnoser
version: 1.0.0
---

# error-immunity

把「同一类错反复发作」当成抗原，用带诱饵选项的陷阱题接种，练到不再咬钩。

## 输入

- 错题记录（错因、知识板块）
- 用户选择：指纹、作答选项

## 输出

- 错误指纹清单（错因 × 板块，出现 ≥2 次才立项）
- 陷阱题（4 选项，含一个专门骗该错因的诱饵）
- 抗体浓度、状态（未接种 / 建立中 / 抗体偏弱 / 复发预警 / 已免疫）
- 接种台账

## 规则

1. 指纹是计数事实：同一格 2 次以上才立项，不猜心理、不做诊断。
2. 诱饵与正确答案在出题时写死（`trap_key` / `correct_key`），作答只做键比对，**判定不经过模型**。
3. 模型只写题面，输出需通过结构校验（4 个选项、键唯一、诱饵≠正确、选项不重复），挡不住就重演用户原题。
4. 一次训练只能答一次，答完才揭晓哪个是诱饵。
5. 连续守住 3 次记「已免疫」，14 天不练开始衰减，最近一次中招记「复发预警」。

## 实现位置

- 接口：`GET /api/teaching/immune/fingerprints`、`POST /api/teaching/immune/drill`、`POST /api/teaching/immune/answer`、`GET /api/teaching/immune/profile`
- 服务：`backend/app/services/reverse_teaching.py`
- 页面：练习与复盘 → 讲与判 → 错误免疫
