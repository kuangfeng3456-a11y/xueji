"""v2.0 P1 算法增强：蒙特卡洛区间（A6）、阶段状态机（A7）、疲劳/负荷公式（A8）。"""

import math
import random
from datetime import date, timedelta
from typing import Dict, List, Optional

PHASES = [
    {"key": "foundation", "label": "基础期", "min_days": 46},
    {"key": "reinforce", "label": "强化期", "min_days": 15},
    {"key": "sprint", "label": "冲刺期", "min_days": 4},
    {"key": "final", "label": "考前 3 日", "min_days": 0},
]
PHASE_CONFIG = {
    "foundation": {"ratio": "新学 60% / 练习 25% / 复习 15%", "target_retention": 0.85, "total_factor": 1.0},
    "reinforce": {"ratio": "新学 35% / 练习 40% / 复习 25%", "target_retention": 0.90, "total_factor": 1.0},
    "sprint": {"ratio": "新学 10% / 练习 55% / 复习 35%", "target_retention": 0.95, "total_factor": 1.0},
    "final": {"ratio": "新学 0% / 练习 30% / 复习 70%", "target_retention": 0.95, "total_factor": 0.6},
}


def phase_for(days_left_count: int) -> Dict:
    days = max(int(days_left_count), 0)
    chosen = PHASES[-1]
    for item in PHASES:
        if days >= item["min_days"]:
            chosen = item
            break
    cfg = PHASE_CONFIG[chosen["key"]]
    return {
        "phase": chosen["key"],
        "label": chosen["label"],
        "days_left": days,
        "ratio": cfg["ratio"],
        "target_retention": cfg["target_retention"],
        "total_factor": cfg["total_factor"],
        "version": "phase-machine-v1",
    }


def monte_carlo_exam_score(
    knowledge: List[Dict],
    completion_rate: float = 0.6,
    tasks_per_day: int = 3,
    eta: float = 0.18,
    days_left_count: int = 40,
    target_score: float = 60.0,
    samples: int = 1000,
    seed: int = 42,
) -> Dict:
    """考试日得分区间（文档 5.7）：掌握度后验抽样 + Beta 完成率 + 逐日推演 + 保持率折损。

    knowledge: [{kp_id, weight, mastery, uncertainty, stability_days}]
    输出百分制 P10/P50/P90 与达标概率；随机种子固定，结果可复现。
    """
    rng = random.Random(seed)
    horizon = max(int(days_left_count), 0)
    items = [dict(item) for item in knowledge if item.get("weight", 0) > 0]
    if not items:
        return {
            "p10": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "score_p10": 0.0,
            "score_p50": 0.0,
            "score_p90": 0.0,
            "probability_to_target": 0.0,
            "target_score": target_score,
            "samples": max(samples, 100),
            "seed": seed,
            "days_left": horizon,
            "method": "monte-carlo-exam-v2",
            "reproducible": True,
            "note": "没有知识点权重，无法给出预测区间。",
        }

    total_weight = sum(float(item["weight"]) for item in items)
    for item in items:
        item["weight"] = float(item["weight"]) / total_weight
        item["mastery"] = min(1.0, max(0.0, float(item.get("mastery", 0.0))))
        item["uncertainty"] = max(0.01, float(item.get("uncertainty", 0.15)))
        item["stability"] = max(1.0, float(item.get("stability_days", 1.0)))

    done = int(round(min(max(completion_rate, 0.0), 1.0) * 20))
    undone = 20 - done
    total_tasks = max(1, tasks_per_day) * max(horizon, 1)

    scores: List[float] = []
    for _ in range(max(samples, 100)):
        mastery = [
            min(1.0, max(0.0, rng.gauss(item["mastery"], item["uncertainty"]))) for item in items
        ]
        daily_rate = rng.betavariate(done + 1, undone + 1)
        for _day in range(horizon):
            for _task in range(max(1, tasks_per_day)):
                if rng.random() >= daily_rate:
                    continue
                # 按“权重 × 薄弱度”挑一个知识点练，收益用 η 折算
                weights = [item["weight"] * (1 - m) for item, m in zip(items, mastery)]
                pick = rng.choices(range(len(items)), weights=weights, k=1)[0]
                mastery[pick] = min(1.0, mastery[pick] + eta * (1 - mastery[pick]))
        total = 0.0
        for item, m in zip(items, mastery):
            # 按复习计划，考试前最后一次复习距考试最多一个稳定度周期，
            # 因此 R(考试日) = 0.9^(min(剩余天数, S)/S)，下限 0.9
            keep = 0.9 ** (min(horizon, item["stability"]) / item["stability"])
            total += item["weight"] * m * keep
        scores.append(round(100 * total, 2))

    scores.sort()

    def percentile(p: float) -> float:
        index = min(len(scores) - 1, max(0, int(len(scores) * p)))
        return round(scores[index], 1)

    reach = len([value for value in scores if value >= target_score]) / len(scores)
    return {
        "p10": percentile(0.10) / 100,
        "p50": percentile(0.50) / 100,
        "p90": percentile(0.90) / 100,
        "score_p10": percentile(0.10),
        "score_p50": percentile(0.50),
        "score_p90": percentile(0.90),
        "probability_to_target": round(reach, 3),
        "target_score": round(target_score, 1),
        "samples": max(samples, 100),
        "seed": seed,
        "days_left": horizon,
        "tasks_per_day": max(1, tasks_per_day),
        "eta": eta,
        "method": "monte-carlo-exam-v2",
        "reproducible": True,
        "note": "预测只用区间表达，不做单点承诺；样本越少区间越宽。",
    }


def monte_carlo_forecast(
    current_mastery: float,
    uncertainty: float,
    daily_gain: float,
    days_left_count: int,
    target: float = 0.7,
    samples: int = 1000,
    seed: int = 42,
) -> Dict:
    rng = random.Random(seed)
    current = min(1.0, max(0.0, current_mastery))
    spread = max(uncertainty, 0.01)
    gain = daily_gain
    horizon = max(int(days_left_count), 0)
    outcomes: List[float] = []
    for _ in range(max(samples, 100)):
        start = min(1.0, max(0.0, rng.gauss(current, spread)))
        drift = rng.gauss(gain, max(abs(gain) * 0.5, 0.004)) * horizon
        outcomes.append(min(1.0, max(0.0, start + drift)))
    outcomes.sort()

    def pct(p: float) -> float:
        index = min(len(outcomes) - 1, max(0, int(len(outcomes) * p)))
        return round(outcomes[index], 4)

    reach = len([value for value in outcomes if value >= target]) / len(outcomes)
    return {
        "p10": pct(0.10),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "probability_to_target": round(reach, 3),
        "target": target,
        "samples": max(samples, 100),
        "seed": seed,
        "method": "monte-carlo-v1",
        "reproducible": True,
    }


def fatigue_index(
    interruptions: int = 0,
    sessions: int = 0,
    leave_minutes: float = 0.0,
    focus_minutes: float = 0.0,
    recent_error_rate: float = 0.0,
    baseline_error_rate: float = 0.0,
    streak_days: int = 0,
) -> Dict:
    """疲劳指数（文档 5.6）：F = 100×(0.30I + 0.25A + 0.25E + 0.20S)。

    I 专注中断率、A 离开页面占比、E 错题率上升、S 连续学习压力；四个分量都归一到 0–1。
    离开时长按“每次离开约 2 分钟”估算（前端未单独上报离开时长），结果里如实标注。
    """
    interruption_rate = min(1.0, max(interruptions, 0) / sessions) if sessions else 0.0
    away_ratio = min(1.0, max(leave_minutes, 0.0) / focus_minutes) if focus_minutes else 0.0
    error_rise = max(0.0, min(1.0, (recent_error_rate - baseline_error_rate) / 0.3))
    streak_pressure = min(1.0, max(streak_days, 0) / 14)
    score = 100 * (
        0.30 * interruption_rate
        + 0.25 * away_ratio
        + 0.25 * error_rise
        + 0.20 * streak_pressure
    )
    if score < 35:
        level = "低"
        suggestion = "当前疲劳可控，按计划执行即可。"
    elif score <= 60:
        level = "中"
        suggestion = "建议把今日任务降为精简档，并插入一次短休息。"
    else:
        level = "高"
        suggestion = "建议立即降档：今日只保留 1 个最小任务，并进入 5 分钟恢复站。"
    return {
        "index": round(score, 1),
        "level": level,
        "suggestion": suggestion,
        "components": {
            "I_interruption_rate": round(interruption_rate, 3),
            "A_away_ratio": round(away_ratio, 3),
            "E_error_rise": round(error_rise, 3),
            "S_streak_pressure": round(streak_pressure, 3),
            "interruptions": max(interruptions, 0),
            "sessions": max(sessions, 0),
            "focus_minutes": round(max(focus_minutes, 0.0), 1),
            "leave_minutes_estimated": round(max(leave_minutes, 0.0), 1),
            "streak_days": max(streak_days, 0),
        },
        "formula": "F = 100×(0.30·I + 0.25·A + 0.25·E + 0.20·S)，I/A/E/S ∈ [0,1]",
        "note": "离开时长按每次约 2 分钟估算，属近似口径。",
        "version": "fatigue-v2",
    }


def cognitive_load(
    planned_minutes: int,
    daily_minutes: int,
    fatigue: float,
    mistake_rate: float = 0.0,
    avg_difficulty: float = 3.0,
) -> Dict:
    """认知负荷（文档 5.6）：L = 0.5·(计划/可用) + 0.3·(难度/5) + 0.2·(F/100)。"""
    ratio = max(planned_minutes, 0) / max(daily_minutes, 1)
    difficulty = max(0.0, min(5.0, avg_difficulty))
    load = (
        0.5 * ratio
        + 0.3 * (difficulty / 5)
        + 0.2 * (max(fatigue, 0.0) / 100)
    )
    index = round(min(100.0, load * 100), 1)
    if load > 0.9:
        level = "高"
        suggestion = "负荷偏高：建议降载，压缩低优先级任务，保留高收益任务。"
    elif load < 0.5 and fatigue < 35:
        level = "低"
        suggestion = "负荷较低且疲劳不高：可适度加难或增加一个练习任务。"
    else:
        level = "中"
        suggestion = "负荷适中：按当前顺序执行，注意中途休息。"
    return {
        "index": index,
        "l": round(load, 3),
        "level": level,
        "load_ratio": round(ratio, 3),
        "difficulty": round(difficulty, 2),
        "suggestion": suggestion,
        "mistake_rate": round(max(mistake_rate, 0), 3),
        "formula": "L = 0.5·(今日计划分钟/可用分钟) + 0.3·(任务难度均值/5) + 0.2·(F/100)；L>0.9 建议降载",
        "version": "load-v2",
    }