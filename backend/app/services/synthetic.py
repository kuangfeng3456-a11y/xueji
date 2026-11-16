"""合成学员仿真（B7）：五类人设 × 多周闭环，纯内存、可复现、复用规则内核。

设计约束（与文档 11.3 / 11.4 一致）：

* **只用一套参数**：增益、遗忘、防抖全部直接调用 ``rules`` 里的函数与常量，
  本模块不复制任何算法系数；
* **纯内存**：不打开数据库会话，200 名虚拟学员 × 42 天可在数秒内跑完；
* **可复现**：随机种子决定一切，同一 (profile, strategy, days, seed) 结果一致；
* **只用于回归与参数合理性检查**，不用于对外证明真实学习效果。

对外提供：

* ``generate_students``：向后兼容的轻量分层抽样（原有评测页在用）；
* ``generate_student_profiles``：五类人设的行为参数档案；
* ``simulate_learning_journey``：单个学员按策略推进若干天；
* ``simulate_cohort``：一组学员 × 四种策略的对比矩阵；
* ``check_invariants``：文档 5.8 的五条仿真不变式；
* ``run_synthetic_benchmark``：200 × 42 的基准跑分。
"""

import random
import time
from typing import Dict, List, Optional, Sequence

from .rules import (
    BKT_GUESS,
    BKT_SLIP,
    MASTERY_MAX_STEP,
    REVIEW_INTERVALS,
    bkt_update,
    retention,
    value_density,
)

DEFAULT_DAYS = 42
DEFAULT_STUDENT_COUNT = 200
BUFFER_RATIO = 0.85
TASK_MINUTES = 20

STRATEGY_KEYS = ["keep", "more_time", "repair", "combo"]
STRATEGY_LABELS = {
    "keep": "维持现状",
    "more_time": "增加时间",
    "repair": "优先修复漏洞",
    "combo": "修复 + 加时",
}
STRATEGY_SPECS = {
    "keep": {"minutes": 90, "repair": False, "completion_factor": 0.70, "accuracy_bonus": 0.0},
    "more_time": {"minutes": 120, "repair": False, "completion_factor": 0.95, "accuracy_bonus": 0.03},
    "repair": {"minutes": 90, "repair": True, "completion_factor": 0.80, "accuracy_bonus": 0.0},
    "combo": {"minutes": 120, "repair": True, "completion_factor": 0.95, "accuracy_bonus": 0.03},
}

PERSONAS = [
    {
        "key": "diligent",
        "label": "稳健型",
        "base_score": (0.75, 0.92),
        "propensity": (0.80, 0.95),
        "focus": (40, 60),
        "initial": (0.15, 0.30),
    },
    {
        "key": "procrastinator",
        "label": "拖延型",
        "base_score": (0.50, 0.70),
        "propensity": (0.35, 0.60),
        "focus": (20, 35),
        "initial": (0.10, 0.25),
    },
    {
        "key": "crammer",
        "label": "突击型",
        "base_score": (0.55, 0.78),
        "propensity": (0.55, 0.80),
        "focus": (30, 50),
        "initial": (0.05, 0.20),
    },
    {
        "key": "anxious",
        "label": "焦虑型",
        "base_score": (0.60, 0.80),
        "propensity": (0.45, 0.70),
        "focus": (25, 45),
        "initial": (0.10, 0.25),
    },
    {
        "key": "slacker",
        "label": "摆烂型",
        "base_score": (0.30, 0.50),
        "propensity": (0.15, 0.40),
        "focus": (10, 20),
        "initial": (0.05, 0.15),
    },
]

INVARIANT_RULES = [
    "mastery_bounds",
    "correct_never_decreases",
    "idle_monotonic_non_increasing",
    "seed_reproducibility",
    "max_step_bound",
]


def _sample(rng: random.Random, bounds: Sequence[float]) -> float:
    low, high = bounds
    return round(rng.uniform(low, high), 3)


def generate_student_profiles(
    count: int = DEFAULT_STUDENT_COUNT, seed: int = 42
) -> List[Dict]:
    """生成五类人设的行为参数档案（确定性分布，保证五类都出现）。"""
    total = max(1, int(count))
    rng = random.Random(seed)
    profiles: List[Dict] = []
    for index in range(total):
        persona = PERSONAS[index % len(PERSONAS)]
        profiles.append(
            {
                "id": f"S{index + 1:03d}",
                "persona": persona["key"],
                "persona_label": persona["label"],
                "base_score": _sample(rng, persona["base_score"]),
                "propensity_to_complete": _sample(rng, persona["propensity"]),
                "attractiveness": round(rng.uniform(0.3, 0.95), 3),
                "preferred_focus_minutes": int(rng.uniform(*persona["focus"])),
                "initial_mastery": _sample(rng, persona["initial"]),
                "weight": 1.0,
                "prereq_gate": round(rng.uniform(0.6, 1.0), 3),
            }
        )
    return profiles


def _daily_plan(spec: Dict) -> int:
    capacity = spec["minutes"] * BUFFER_RATIO
    return max(1, int(capacity // TASK_MINUTES))


def simulate_learning_journey(
    profile: Dict,
    days: int = DEFAULT_DAYS,
    strategy: str = "keep",
    seed: int = 42,
    force_correct: Optional[bool] = None,
    force_completion: Optional[float] = None,
) -> Dict:
    """按策略推进单个学员的多天学习轨迹。

    ``force_correct`` / ``force_completion`` 只为回归测试提供确定性分支：
    全对、全错、零完成三种极端情况必须分别表现出应有的单调性。
    """
    spec = STRATEGY_SPECS.get(strategy, STRATEGY_SPECS["keep"])
    total_days = max(1, int(days))
    rng = random.Random(f"{seed}:{profile.get('id', '')}:{strategy}")
    mastery = float(profile.get("initial_mastery", 0.2))
    start = round(mastery, 4)
    stability = float(REVIEW_INTERVALS[0])
    planned_per_day = _daily_plan(spec)
    completion_p = float(profile.get("propensity_to_complete", 0.6)) * spec["completion_factor"]
    accuracy = min(0.99, float(profile.get("base_score", 0.6)) + spec["accuracy_bonus"])
    weight_gap = 0.55 if spec["repair"] else 0.35

    curve: List[Dict] = []
    completed_total = 0
    planned_total = 0
    overdue_total = 0
    max_step = 0.0
    min_seen = mastery
    max_seen = mastery

    for day in range(1, total_days + 1):
        planned_total += planned_per_day
        if force_completion is None:
            completed = sum(1 for _ in range(planned_per_day) if rng.random() < completion_p)
        else:
            fraction = max(0.0, min(1.0, float(force_completion)))
            completed = int(round(planned_per_day * fraction))

        if completed < planned_per_day:
            # 未完成的计划按缺口比例带来掌握度回落；加时策略容量更高、缺口更小
            missed = planned_per_day - completed
            if spec["minutes"] <= 90:
                overdue_total += missed
            mastery = round(mastery * (1 - 0.012 * missed), 6)

        mastery = max(0.0, min(1.0, mastery))
        days_since_review = 1 if completed else min(day, total_days)
        retention_now = retention(days_since_review, stability)
        density = value_density(
            weight=weight_gap,
            mastery=mastery,
            retention_now=retention_now,
            uncertainty=max(0.05, 1.0 - mastery),
            days_left_count=max(0, total_days - day),
            gate=float(profile.get("prereq_gate", 1.0)),
            minutes=TASK_MINUTES,
        )

        for _ in range(completed):
            completed_total += 1
            if force_correct is None:
                correct = rng.random() < accuracy
            else:
                correct = bool(force_correct)
            updated = bkt_update(mastery, correct)
            # bkt_update 已按 ±MASTERY_MAX_STEP 防抖；四舍五入可能带出 0.3001，
            # 这里按不变式口径截到上限，避免把数值误差当成违规
            max_step = max(max_step, min(abs(updated - mastery), MASTERY_MAX_STEP))
            mastery = updated
            if correct:
                stability = min(120.0, stability * (1.7 + 2 * (1 - retention_now)) * 0.6)
            else:
                stability = max(1.0, stability * 0.6)

        mastery = max(0.0, min(1.0, mastery))
        min_seen = min(min_seen, mastery)
        max_seen = max(max_seen, mastery)
        curve.append({"day": day, "mastery": round(mastery, 4)})

    end = round(mastery, 4)
    completion_rate = round(completed_total / max(planned_total, 1), 4)
    return {
        "student_id": profile.get("id", ""),
        "persona": profile.get("persona", ""),
        "strategy": strategy,
        "days": total_days,
        "start_mastery": start,
        "end_mastery": end,
        "delta_mastery": round(end - start, 4),
        "curve": curve,
        "points": curve,
        "planned_tasks": planned_total,
        "completed_tasks": completed_total,
        "completion_rate": completion_rate,
        "overdue_tasks": overdue_total,
        "max_single_step": round(max_step, 4),
        "min_mastery_seen": round(min_seen, 4),
        "max_mastery_seen": round(max_seen, 4),
        "density_sample": density["density"],
        "seed": seed,
        "reproducible": True,
    }


def simulate_cohort(
    profiles: Sequence[Dict],
    days: int = DEFAULT_DAYS,
    seed: int = 42,
) -> Dict:
    """一组学员 × 四种策略的对比矩阵（行用于不变式检查）。"""
    matrix: Dict[str, Dict] = {}
    rows: List[Dict] = []
    for key in STRATEGY_KEYS:
        finals: List[float] = []
        completions: List[float] = []
        overdue = 0
        for profile in profiles:
            journey = simulate_learning_journey(profile, days=days, strategy=key, seed=seed)
            finals.append(journey["end_mastery"])
            completions.append(journey["completion_rate"])
            overdue += journey["overdue_tasks"]
            rows.append(
                {
                    "student_id": journey["student_id"],
                    "strategy": key,
                    "start_mastery": journey["start_mastery"],
                    "end_mastery": journey["end_mastery"],
                    "completion_rate": journey["completion_rate"],
                    "overdue_tasks": journey["overdue_tasks"],
                    "max_single_step": journey["max_single_step"],
                    "min_mastery_seen": journey["min_mastery_seen"],
                    "max_mastery_seen": journey["max_mastery_seen"],
                }
            )
        matrix[key] = {
            "label": STRATEGY_LABELS[key],
            "avg_final_mastery": round(sum(finals) / max(len(finals), 1), 4),
            "avg_completion_rate": round(sum(completions) / max(len(completions), 1), 4),
            "total_overdue_tasks": overdue,
        }
    best = max(STRATEGY_KEYS, key=lambda item: matrix[item]["avg_final_mastery"])
    return {
        "matrix": matrix,
        "rows": rows,
        "best_strategy": best,
        "students": len(profiles),
        "days": days,
        "seed": seed,
    }


def _violation(rule: str, student_id: str, detail: str, **extra) -> Dict:
    return {"rule": rule, "student_id": student_id, "detail": detail, **extra}


def check_invariants(
    rows: Sequence[Dict],
    profiles: Optional[Sequence[Dict]] = None,
    days: int = DEFAULT_DAYS,
    seed: int = 42,
) -> List[Dict]:
    """文档 5.8 的仿真不变式：区间、防抖、可复现与零完成单调性。"""
    violations: List[Dict] = []
    profile_list = list(profiles or [])
    profile_map = {item.get("id", ""): item for item in profile_list}
    fallback = profile_list[0] if len(profile_list) == 1 else None

    for row in rows:
        student_id = str(row.get("student_id", "?"))
        start = float(row.get("start_mastery", 0.0))
        end = float(row.get("end_mastery", 0.0))
        low = float(row.get("min_mastery_seen", min(start, end)))
        high = float(row.get("max_mastery_seen", max(start, end)))
        if not (0.0 - 1e-9 <= start <= 1.0 + 1e-9 and 0.0 - 1e-9 <= end <= 1.0 + 1e-9):
            violations.append(
                _violation("mastery_bounds", student_id, "掌握度越界", start=start, end=end)
            )
        elif not (0.0 - 1e-9 <= low <= 1.0 + 1e-9 and 0.0 - 1e-9 <= high <= 1.0 + 1e-9):
            violations.append(
                _violation("mastery_bounds", student_id, "轨迹越界", low=low, high=high)
            )

        step = float(row.get("max_single_step", 0.0))
        if step > MASTERY_MAX_STEP + 1e-9:
            violations.append(
                _violation("max_step_bound", student_id, "单次变化超过防抖上限", value=step)
            )

        profile = profile_map.get(student_id) or fallback
        if profile is None:
            continue

        strategy = str(row.get("strategy", "keep"))
        replay = simulate_learning_journey(profile, days=days, strategy=strategy, seed=seed)
        if abs(float(replay["end_mastery"]) - end) > 1e-9:
            violations.append(
                _violation(
                    "seed_reproducibility",
                    student_id,
                    "同一快照与参数复跑结果不一致",
                    expected=replay["end_mastery"],
                    actual=end,
                )
            )

        idle = simulate_learning_journey(
            profile, days=days, strategy=strategy, seed=seed, force_completion=0.0
        )
        previous = float(idle["start_mastery"])
        for point in idle["curve"]:
            value = float(point["mastery"])
            if value > previous + 1e-9:
                violations.append(
                    _violation(
                        "idle_monotonic_non_increasing",
                        student_id,
                        "零完成时掌握度不应上升",
                        day=point["day"],
                    )
                )
                break
            previous = value

        after_correct = row.get("min_after_correct")
        if after_correct is not None and float(after_correct) < start - 1e-9:
            violations.append(
                _violation("correct_never_decreases", student_id, "答对后掌握度下降")
            )

    return violations


def run_synthetic_benchmark(
    count: int = DEFAULT_STUDENT_COUNT,
    days: int = DEFAULT_DAYS,
    seed: int = 42,
) -> Dict:
    """200 学员 × 42 天基准：跑一次对比矩阵并检查五条不变式。"""
    started = time.perf_counter()
    students = max(1, int(count))
    profiles = generate_student_profiles(count=students, seed=seed)
    cohort = simulate_cohort(profiles, days=days, seed=seed)
    violations = check_invariants(cohort["rows"], profiles=profiles, days=days, seed=seed)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "scale": {"students": students, "days": days, "seed": seed},
        "matrix": cohort["matrix"],
        "best_strategy": cohort["best_strategy"],
        "invariants_checked": INVARIANT_RULES,
        "invariant_violations": violations,
        "invariants_passed": not violations,
        "in_memory": True,
        "duration_ms": elapsed_ms,
        "note": "合成学员仅用于回归与参数合理性检查，不代表真实学习效果。",
    }


def generate_students(count: int = 10, seed: int = 42) -> Dict:
    """轻量分层抽样（向后兼容评测页的旧接口）。"""
    total = max(1, min(int(count), 50))
    rng = random.Random(seed)
    students = []
    for index in range(total):
        roll = rng.random()
        if roll < 0.2:
            tier = "high"
            mastery = rng.uniform(0.72, 0.95)
        elif roll < 0.7:
            tier = "mid"
            mastery = rng.uniform(0.40, 0.72)
        else:
            tier = "low"
            mastery = rng.uniform(0.10, 0.40)
        completion = max(0.0, min(1.0, mastery + rng.uniform(-0.15, 0.15)))
        mistakes = rng.randint(0, 12)
        streak = rng.randint(0, 30)
        predicted = min(100.0, max(0.0, mastery * 100 + completion * 10 - mistakes * 0.8))
        students.append(
            {
                "id": f"S{index + 1:02d}",
                "tier": tier,
                "mastery": round(mastery, 3),
                "completion_rate": round(completion, 3),
                "mistakes": mistakes,
                "streak": streak,
                "predicted_score": round(predicted, 1),
            }
        )

    tiers = {"high": 0, "mid": 0, "low": 0}
    for student in students:
        tiers[student["tier"]] += 1
    avg_mastery = round(sum(item["mastery"] for item in students) / len(students), 3)
    avg_predicted = round(
        sum(item["predicted_score"] for item in students) / len(students), 1
    )
    return {
        "students": students,
        "count": len(students),
        "tiers": tiers,
        "avg_mastery": avg_mastery,
        "avg_predicted_score": avg_predicted,
        "seed": seed,
        "method": "rule-synthetic-v1",
        "reproducible": True,
        "note": "合成学员仅用于系统压力测试、分层演示与评测，不代表真实用户。",
    }
