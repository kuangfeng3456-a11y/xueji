from datetime import date, datetime, timedelta

import pytest

from app.services import rules


def test_clamp_respects_bounds():
    assert rules.clamp(1.5) == 1.0
    assert rules.clamp(-0.2) == 0.0
    assert rules.clamp(0.4) == 0.4
    assert rules.clamp(5, 1, 3) == 3


def test_update_mastery_follows_alpha_formula():
    assert rules.update_mastery(0.0, True) == 0.3
    assert rules.update_mastery(0.5, True) == 0.65
    assert rules.update_mastery(0.5, False) == 0.35
    assert rules.update_mastery(0.0, False) == 0.0
    assert rules.update_mastery(1.0, True) == 1.0


def test_next_review_date_progresses_and_resets():
    today = date(2026, 1, 1)
    day, stage = rules.next_review_date(True, 0, today)
    assert (day, stage) == (date(2026, 1, 3), 1)

    day, stage = rules.next_review_date(True, 3, today)
    assert (day, stage) == (date(2026, 1, 16), 4)

    # 已到最长间隔仍答对时停留在最后一级
    day, stage = rules.next_review_date(True, 4, today)
    assert (day, stage) == (date(2026, 1, 16), 4)

    # 答错回到 1 天
    day, stage = rules.next_review_date(False, 4, today)
    assert (day, stage) == (date(2026, 1, 2), 0)


def test_urgency_coefficient_grows_near_exam():
    near = rules.urgency_coefficient(0)
    mid = rules.urgency_coefficient(14)
    far = rules.urgency_coefficient(365)
    assert near == 4.0
    assert far == 1.0
    assert far < mid < near
    assert rules.urgency_coefficient(-5) == 4.0


def test_task_priority_formula_and_floors():
    # 权重 2 × (1-0.5) × 临近系数
    assert rules.task_priority(2.0, 0.5, 14) == round(2 * 0.5 * rules.urgency_coefficient(14), 3)
    # 权重下限 0.1，掌握度上限 1.0（未掌握比例下限 0.05）
    assert rules.task_priority(-3, 2.0, 30) == round(0.1 * 0.05 * rules.urgency_coefficient(30), 3)


def test_days_left_helpers_never_negative():
    today = date(2026, 5, 1)
    assert rules.days_left(date(2026, 5, 11), today) == 10
    assert rules.days_left(date(2026, 4, 1), today) == 0
    assert rules.plan_days_left(date(2026, 5, 11), today) == 10
    assert rules.plan_days_left(today, today) == 1


def test_completion_rate_handles_zero_total():
    assert rules.completion_rate(3, 4) == 0.75
    assert rules.completion_rate(0, 0) == 0.0
    assert rules.completion_rate(5, 0) == 0.0


def test_week_bounds_starts_on_monday():
    start, end = rules.week_bounds(date(2026, 11, 7))  # 周六
    assert start == date(2026, 11, 2)
    assert end == date(2026, 11, 8)
    assert start.weekday() == 0


def test_calc_streak_variants():
    today = date(2026, 11, 7)
    assert rules.calc_streak([today, today - timedelta(days=1)], today) == 2
    # 今天未打卡时从昨天回溯
    assert rules.calc_streak([today - timedelta(days=1), today - timedelta(days=2)], today) == 2
    # 断档后只算连续部分
    assert rules.calc_streak([today - timedelta(days=2)], today) == 0
    assert rules.calc_streak([], today) == 0


def test_text_similarity_bounds():
    assert rules.text_similarity("", "abc") == 0.0
    assert rules.text_similarity("abc", "") == 0.0
    assert rules.text_similarity("Hello", "hello ") == 1.0
    assert 0 < rules.text_similarity("absence", "absent") < 1


@pytest.mark.parametrize(
    "question,user_answer,correct_answer,expected",
    [
        ("听力第三题", "", "A", "time"),
        ("听力第三题", "时间不够，空着", "A", "time"),
        ("听力第三题", "She is not sure about time", "She is not sure about the time", "careless"),
        ("请计算该极限的值", "做不到", "0", "method"),
        ("以下哪个选项正确", "不会", "B", "concept"),
        ("下列哪个选项正确", "完全不同的答案", "B", "concept"),
        ("翻译这句话", "随便写了一点", "标准译文", "method"),
    ],
)
def test_classify_mistake_categories(question, user_answer, correct_answer, expected):
    category, label, suggestion = rules.classify_mistake(question, user_answer, correct_answer)
    assert category == expected
    assert label == rules.MISTAKE_CATEGORIES[expected]
    assert suggestion


def test_classify_mistake_with_empty_inputs_falls_back_to_time():
    category, label, _ = rules.classify_mistake("", "", "")
    assert category == "time"
    assert label == "时间不够"


def test_difficulty_label_thresholds():
    assert rules.difficulty_label(0.1) == "薄弱"
    assert rules.difficulty_label(0.34) == "薄弱"
    assert rules.difficulty_label(0.35) == "待巩固"
    assert rules.difficulty_label(0.69) == "待巩固"
    assert rules.difficulty_label(0.7) == "已掌握"


def test_pick_weak_points_sorted_by_value_then_weight():
    items = [
        {"name": "a", "value": 0.5, "weight": 1.0},
        {"name": "b", "value": 0.2, "weight": 2.0},
        {"name": "c", "value": 0.2, "weight": 3.0},
        {"name": "d", "value": 0.9, "weight": 1.0},
    ]
    picked = rules.pick_weak_points(items, limit=2)
    assert [item["name"] for item in picked] == ["c", "b"]


def test_distribute_minutes_balances_remainder():
    assert rules.distribute_minutes(90, 3) == [30, 30, 30]
    assert rules.distribute_minutes(100, 3) == [34, 33, 33]
    assert rules.distribute_minutes(1, 3) == [1, 0, 0]
    assert rules.distribute_minutes(10, 0) == []


def test_task_type_and_category_catalogues_are_complete():
    assert set(rules.TASK_TYPES) == {"study", "review", "practice", "remedial"}
    assert set(rules.MISTAKE_CATEGORIES) == {"concept", "method", "careless", "time"}
    assert rules.REVIEW_INTERVALS == [1, 2, 4, 7, 15]
    assert isinstance(datetime.utcnow(), datetime)