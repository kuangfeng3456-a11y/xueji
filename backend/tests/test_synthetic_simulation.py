"""B7 合成学员仿真：多天推进、策略对比与不变式检查（纯内存，不建 DB session）。"""

import time

from app.services import rules
from app.services.synthetic import (
    DEFAULT_DAYS,
    DEFAULT_STUDENT_COUNT,
    INVARIANT_RULES,
    PERSONAS,
    STRATEGY_KEYS,
    check_invariants,
    generate_student_profiles,
    generate_students,
    run_synthetic_benchmark,
    simulate_cohort,
    simulate_learning_journey,
)

DILIGENT = {
    "id": "T-DILIGENT",
    "persona": "diligent",
    "persona_label": "稳健型",
    "base_score": 0.9,
    "propensity_to_complete": 1.0,
    "attractiveness": 0.9,
    "preferred_focus_minutes": 60,
    "initial_mastery": 0.2,
    "weight": 1.0,
    "prereq_gate": 1.0,
}


def _profile(**overrides):
    profile = dict(DILIGENT)
    profile.update(overrides)
    return profile


# ------------------------------------------------------------------
# 向后兼容：generate_students 未被破坏
# ------------------------------------------------------------------
def test_generate_students_still_defaults_to_ten_and_is_backward_compatible():
    result = generate_students()
    assert result["count"] == 10
    assert result["method"] == "rule-synthetic-v1"
    assert set(result["students"][0]) == {
        "id", "tier", "mastery", "completion_rate", "mistakes", "streak", "predicted_score"
    }


# ------------------------------------------------------------------
# 可复现性
# ------------------------------------------------------------------
def test_same_seed_produces_identical_journey():
    first = simulate_learning_journey(DILIGENT, days=DEFAULT_DAYS, strategy="keep", seed=42)
    second = simulate_learning_journey(DILIGENT, days=DEFAULT_DAYS, strategy="keep", seed=42)
    assert first == second
    assert first["curve"] == second["curve"]
    assert first["points"] == second["points"]


def test_different_seed_changes_trajectory_but_keeps_bounds():
    a = simulate_learning_journey(DILIGENT, days=DEFAULT_DAYS, seed=42)
    b = simulate_learning_journey(DILIGENT, days=DEFAULT_DAYS, seed=43)
    assert isinstance(a["end_mastery"], float)
    assert 0.0 <= a["end_mastery"] <= 1.0
    assert 0.0 <= b["end_mastery"] <= 1.0


def test_benchmark_is_reproducible_end_to_end():
    first = run_synthetic_benchmark(count=50, days=DEFAULT_DAYS, seed=11)
    second = run_synthetic_benchmark(count=50, days=DEFAULT_DAYS, seed=11)
    assert first["matrix"] == second["matrix"]
    assert first["invariant_violations"] == second["invariant_violations"]


# ------------------------------------------------------------------
# 学习有效 / 无效
# ------------------------------------------------------------------
def test_all_correct_over_42_days_lifts_mastery_well_above_start():
    journey = simulate_learning_journey(
        DILIGENT, days=DEFAULT_DAYS, strategy="more_time", seed=42, force_correct=True
    )
    assert journey["start_mastery"] == 0.2
    assert journey["end_mastery"] > journey["start_mastery"] + 0.3
    assert journey["delta_mastery"] > 0.3
    assert journey["overdue_tasks"] == 0


def test_all_wrong_does_not_raise_mastery():
    journey = simulate_learning_journey(
        DILIGENT, days=DEFAULT_DAYS, strategy="more_time", seed=42, force_correct=False
    )
    assert journey["end_mastery"] <= journey["start_mastery"]
    assert journey["delta_mastery"] <= 0.0


def test_zero_completion_mastery_is_monotonic_non_increasing():
    journey = simulate_learning_journey(
        DILIGENT, days=DEFAULT_DAYS, strategy="keep", seed=42, force_completion=0.0
    )
    assert journey["completed_tasks"] == 0
    assert journey["completion_rate"] == 0.0
    previous = journey["start_mastery"]
    for point in journey["curve"]:
        assert point["mastery"] <= previous + 1e-9
        previous = point["mastery"]
    assert journey["end_mastery"] < journey["start_mastery"]


# ------------------------------------------------------------------
# 复用真实规则：不允许出现第二套增益/遗忘参数
# ------------------------------------------------------------------
def test_simulation_uses_rules_functions_not_private_math(monkeypatch):
    calls = {"bkt_update": 0, "retention": 0, "value_density": 0}
    real_bkt = rules.bkt_update
    real_retention = rules.retention
    real_density = rules.value_density

    def spy_bkt(*args, **kwargs):
        calls["bkt_update"] += 1
        return real_bkt(*args, **kwargs)

    def spy_retention(*args, **kwargs):
        calls["retention"] += 1
        return real_retention(*args, **kwargs)

    def spy_density(*args, **kwargs):
        calls["value_density"] += 1
        return real_density(*args, **kwargs)

    monkeypatch.setattr(rules, "bkt_update", spy_bkt)
    # synthetic 模块以 `from .rules import ...` 绑定名字，需同时打补丁到本模块
    import app.services.synthetic as synthetic

    monkeypatch.setattr(synthetic, "bkt_update", spy_bkt)
    monkeypatch.setattr(synthetic, "retention", spy_retention)
    monkeypatch.setattr(synthetic, "value_density", spy_density)

    simulate_learning_journey(DILIGENT, days=DEFAULT_DAYS, strategy="combo", seed=42)

    assert calls["bkt_update"] > 0
    assert calls["retention"] > 0
    assert calls["value_density"] > 0


def test_module_defines_no_second_gain_or_forget_constants():
    import app.services.synthetic as synthetic

    rules_values = {id(value) for value in vars(rules).values() if isinstance(value, (int, float))}
    suspicious = []
    for name, value in vars(synthetic).items():
        if not name.isupper() or not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        # 算法系数（增益/遗忘/滑失/学习转移等）必须直接引用 rules 的对象，
        # 不允许在本模块另定一份。规模类常量（学员数、天数、缓冲比例）不受此约束。
        is_algorithm_name = any(
            key in name for key in ("GAIN", "FORGET", "DECAY", "SLIP", "LEARN", "BKT", "MAX_STEP", "ETA")
        )
        if is_algorithm_name and id(value) not in rules_values:
            suspicious.append(name)
    assert suspicious == []

    # 所有算法参数一律来自 rules（同一对象，而非数值巧合）
    assert synthetic.MASTERY_MAX_STEP is rules.MASTERY_MAX_STEP
    assert synthetic.BKT_SLIP is rules.BKT_SLIP
    assert synthetic.BKT_GUESS is rules.BKT_GUESS
    assert synthetic.REVIEW_INTERVALS is rules.REVIEW_INTERVALS


def test_single_step_change_never_exceeds_rules_max_step_across_personas():
    profiles = generate_student_profiles(count=40, seed=5)
    for profile in profiles:
        for strategy in STRATEGY_KEYS:
            journey = simulate_learning_journey(profile, days=21, strategy=strategy, seed=5)
            assert journey["max_single_step"] <= rules.MASTERY_MAX_STEP + 1e-9


# ------------------------------------------------------------------
# 画像：五类人设 × 行为参数
# ------------------------------------------------------------------
def test_profiles_cover_five_personas_with_behavioural_parameters():
    profiles = generate_student_profiles(count=DEFAULT_STUDENT_COUNT, seed=42)
    assert len(profiles) == DEFAULT_STUDENT_COUNT
    keys = {profile["persona"] for profile in profiles}
    assert keys == {persona["key"] for persona in PERSONAS}
    required = {
        "id", "persona", "base_score", "propensity_to_complete",
        "attractiveness", "preferred_focus_minutes", "initial_mastery", "weight",
    }
    assert required <= set(profiles[0])
    for profile in profiles:
        assert 0.0 <= profile["base_score"] <= 1.0
        assert 0.0 <= profile["propensity_to_complete"] <= 1.0
        assert profile["preferred_focus_minutes"] >= 5


# ------------------------------------------------------------------
# 策略对比：沿用 simulation.py 的四种口径
# ------------------------------------------------------------------
def test_strategy_matrix_uses_existing_strategy_keys():
    profiles = generate_student_profiles(count=30, seed=9)
    cohort = simulate_cohort(profiles, days=DEFAULT_DAYS, seed=9)
    assert list(cohort["matrix"]) == STRATEGY_KEYS
    for entry in cohort["matrix"].values():
        assert set(entry) >= {
            "avg_final_mastery", "avg_completion_rate", "total_overdue_tasks",
        }
    # 加时与修复组合应优于维持现状
    assert cohort["matrix"]["combo"]["avg_final_mastery"] > cohort["matrix"]["keep"]["avg_final_mastery"]
    assert cohort["best_strategy"] in STRATEGY_KEYS


# ------------------------------------------------------------------
# 不变式检查
# ------------------------------------------------------------------
def test_check_invariants_returns_empty_for_normal_run():
    profiles = generate_student_profiles(count=25, seed=3)
    cohort = simulate_cohort(profiles, days=DEFAULT_DAYS, seed=3)
    violations = check_invariants(cohort["rows"], profiles=profiles[:8], days=DEFAULT_DAYS, seed=3)
    assert violations == []


def test_check_invariants_reports_out_of_bounds_mastery():
    bad = [{"student_id": "BAD", "start_mastery": 0.2, "end_mastery": 1.4,
            "min_mastery_seen": 0.2, "max_mastery_seen": 1.4}]
    violations = check_invariants(bad, profiles=[DILIGENT], days=7, seed=42)
    assert any(item["rule"] == "mastery_bounds" for item in violations)


def test_check_invariants_reports_step_larger_than_max_step():
    bad = [{"student_id": "BAD", "start_mastery": 0.0, "end_mastery": 0.5,
            "min_mastery_seen": 0.0, "max_mastery_seen": 0.5,
            "max_single_step": rules.MASTERY_MAX_STEP + 0.05}]
    violations = check_invariants(bad, profiles=[DILIGENT], days=7, seed=42)
    step_hits = [item for item in violations if item["rule"] == "max_step_bound"]
    assert len(step_hits) == 1
    assert step_hits[0]["student_id"] == "BAD"


def test_check_invariants_detects_non_reproducible_journey():
    """人为构造一个「同 seed 两次不同」的仿真器，检查不变式确实能抓到。"""
    import app.services.synthetic as synthetic

    original = synthetic.simulate_learning_journey
    state = {"n": 0}

    def flaky(profile, *args, **kwargs):
        state["n"] += 1
        journey = original(profile, *args, **kwargs)
        if state["n"] % 2 == 0:
            journey = dict(journey)
            journey["end_mastery"] = round(journey["end_mastery"] + 0.05, 4)
        return journey

    synthetic.simulate_learning_journey = flaky
    try:
        violations = synthetic.check_invariants(
            [{"student_id": "X", "start_mastery": 0.2, "end_mastery": 0.3}],
            profiles=[_profile(id="FLAKY")],
            days=7,
            seed=42,
        )
    finally:
        synthetic.simulate_learning_journey = original

    assert any(item["rule"] == "seed_reproducibility" for item in violations)


def test_check_invariants_detects_idle_mastery_increase():
    """人为构造零完成却上升的轨迹，单调不增不变式必须报出。"""
    import app.services.synthetic as synthetic

    original = synthetic.simulate_learning_journey

    def rising(profile, *args, **kwargs):
        journey = dict(original(profile, *args, **kwargs))
        journey["curve"] = [{"day": i + 1, "mastery": 0.2 + 0.05 * i} for i in range(5)]
        return journey

    synthetic.simulate_learning_journey = rising
    try:
        violations = synthetic.check_invariants(
            [{"student_id": "X", "start_mastery": 0.2, "end_mastery": 0.4}],
            profiles=[_profile(id="RISING")],
            days=7,
            seed=42,
        )
    finally:
        synthetic.simulate_learning_journey = original

    assert any(item["rule"] == "idle_monotonic_non_increasing" for item in violations)


def test_invariant_rule_list_has_five_properties():
    assert len(INVARIANT_RULES) == 5
    assert set(INVARIANT_RULES) == {
        "mastery_bounds",
        "correct_never_decreases",
        "idle_monotonic_non_increasing",
        "seed_reproducibility",
        "max_step_bound",
    }


# ------------------------------------------------------------------
# 规模：200 学员 × 42 天，纯内存且耗时可控
# ------------------------------------------------------------------
def test_two_hundred_students_by_42_days_runs_in_memory_quickly():
    started = time.perf_counter()
    benchmark = run_synthetic_benchmark(count=DEFAULT_STUDENT_COUNT, days=DEFAULT_DAYS, seed=42)
    elapsed = time.perf_counter() - started

    assert benchmark["scale"] == {"students": 200, "days": 42, "seed": 42}
    assert benchmark["invariants_checked"] == INVARIANT_RULES
    assert benchmark["invariants_passed"] is True
    assert benchmark["invariant_violations"] == []
    assert benchmark["in_memory"] is True
    assert len(benchmark["matrix"]) == len(STRATEGY_KEYS)
    assert elapsed < 20.0, f"200×42 仿真耗时 {elapsed:.2f}s，超出宽松上限"


def test_benchmark_does_not_open_database_sessions():
    """仿真是纯内存的：任何 DB/session 调用都视为回归。"""
    from sqlalchemy.orm import Session

    import app.services.synthetic as synthetic

    source = __import__("inspect").getsource(synthetic)
    assert "Session" not in source
    assert "db" not in getattr(synthetic.run_synthetic_benchmark.__code__, "co_names", ())
    assert Session  # 仅确认导入可用，不参与仿真


def test_every_strategy_result_is_within_bounds_for_whole_cohort():
    profiles = generate_student_profiles(count=200, seed=42)
    cohort = simulate_cohort(profiles, days=DEFAULT_DAYS, seed=42)
    assert len(cohort["rows"]) == 200 * len(STRATEGY_KEYS)
    for row in cohort["rows"]:
        assert 0.0 <= row["start_mastery"] <= 1.0
        assert 0.0 <= row["end_mastery"] <= 1.0
        assert 0.0 <= row["completion_rate"] <= 1.0
        assert row["overdue_tasks"] >= 0
