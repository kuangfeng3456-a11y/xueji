---
name: cognitive-load
agent: Coach
version: 2.1.0
---

# cognitive-load

根据疲劳、今日任务量与近 7 天错题率计算认知负荷，动态调整任务难度与颗粒度。

## 输入

- 疲劳指数
- 今日任务数量与总时长
- 近 7 天错题率、准备度

## 输出

- 负荷分数（0–100）与等级（low / optimal / high / overload）
- 影响因素
- 建议动作与推荐任务数、分钟数

## 规则

1. 负荷 = 疲劳 × 0.55 + 超量任务惩罚 + 错题率 × 25。
2. overload / high → 降载，只保留 1 个最轻任务。
3. low → 增加 1 个迁移 / 挑战任务。
4. 任务已足够精简时使用「已足够精简」文案，不显示「顺延 0 个」。
5. 调节结果写入学习证据链。

## 实现位置

- `backend/app/services/cognitive_load.py`
- `backend/app/api/evidence.py`
- 前端：驾驶舱认知负荷卡