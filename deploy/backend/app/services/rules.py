"""核心规则引擎：掌握度、复习间隔、任务优先级与错因分类。

这些函数是纯函数，不依赖数据库和大模型，保证答辩演示时结果稳定、可复现。
"""

import difflib
import math
from datetime import date, timedelta
from typing import Iterable, List, Optional, Tuple

MASTERY_ALPHA = 0.3
REVIEW_INTERVALS = [1, 2, 4, 7, 15]
TASK_TYPES = {
    "study": "学习",
    "review": "复习",
    "practice": "练习",
    "remedial": "补救",
}
MISTAKE_CATEGORIES = {
    "concept": "概念不清",
    "method": "方法不会",
    "careless": "粗心",
    "time": "时间不够",
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def update_mastery(old: float, correct: bool) -> float:
    """m_new = m_old + 0.3 * (r - m_old)，答对 r=1，答错 r=0。"""
    r = 1.0 if correct else 0.0
    return round(clamp(old + MASTERY_ALPHA * (r - old)), 4)


def next_review_date(correct: bool, stage: int, today: Optional[date] = None) -> Tuple[date, int]:
    """答对进入下一间隔（1/2/4/7/15 天），答错回到 1 天。"""
    today = today or date.today()
    if correct:
        stage = min(stage + 1, len(REVIEW_INTERVALS) - 1)
    else:
        stage = 0
    return today + timedelta(days=REVIEW_INTERVALS[stage]), stage


def urgency_coefficient(days_left: int) -> float:
    """临近系数：越接近考试越高，范围约 1.0 ~ 4.0。"""
    return round(1 + 3 * math.exp(-max(days_left, 0) / 14), 3)


def task_priority(weight: float, mastery: float, days_left: int) -> float:
    """任务优先级 = 知识点权重 × (1 - 掌握度) × 临近系数。"""
    weight = max(weight, 0.1)
    mastery = clamp(mastery)
    return round(weight * max(1 - mastery, 0.05) * urgency_coefficient(days_left), 3)


def days_left(exam_date: date, today: Optional[date] = None) -> int:
    today = today or date.today()
    return max((exam_date - today).days, 0)


def plan_days_left(exam_date: date, today: Optional[date] = None) -> int:
    """可用于学习的剩余天数（不含考试当天）。"""
    return max((exam_date - (today or date.today())).days, 1)


def completion_rate(done: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(done / total, 4)


def week_bounds(day: Optional[date] = None) -> Tuple[date, date]:
    day = day or date.today()
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def calc_streak(done_days: Iterable[date], today: Optional[date] = None) -> int:
    """统计截至今天的连续打卡天数，今天未打卡则从昨天开始回溯。"""
    today = today or date.today()
    days = set(done_days)
    cursor = today
    if cursor not in days:
        cursor = today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def text_similarity(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def classify_mistake(question: str, user_answer: str, correct_answer: str) -> Tuple[str, str, str]:
    """规则版错因归因，返回 (类别, 标签, 补救建议)。

    四类错因：概念不清、方法不会、粗心、时间不够。
    """
    question = (question or "").strip()
    user_answer = (user_answer or "").strip()
    correct_answer = (correct_answer or "").strip()
    lower_q = question.lower()

    if not user_answer or any(k in user_answer for k in ("没时间", "时间不够", "来不及", "空着", "未作答")):
        return (
            "time",
            MISTAKE_CATEGORIES["time"],
            "今天先做 10 分钟限时训练：每题限时 2 分钟，训练先易后难的答题节奏，超时就先标记跳过。",
        )

    similarity = text_similarity(user_answer, correct_answer)
    if correct_answer and similarity >= 0.75 and user_answer != correct_answer:
        return (
            "careless",
            MISTAKE_CATEGORIES["careless"],
            "答案思路是对的，差在细节。做一道同类题时强制检查单位、符号和题干关键词，养成回看 10 秒的习惯。",
        )

    method_words = ("计算", "求解", "证明", "步骤", "方法", "公式", "推导", "编程", "算法")
    if any(word in question for word in method_words):
        return (
            "method",
            MISTAKE_CATEGORIES["method"],
            "先看例题的解题步骤，再独立重做本题；把关键步骤写成 3 条方法卡片，明天复习时先默写步骤再做题。",
        )

    if any(word in user_answer for word in ("不会", "不知道", "蒙", "猜")):
        return (
            "concept",
            MISTAKE_CATEGORIES["concept"],
            "回到对应知识点，用 5 分钟重读定义并画出概念图，再用 2 道基础题确认理解，最后把易混点写进笔记。",
        )

    if any(word in lower_q for word in ("下列", "选择", "判断", "填空")) and similarity < 0.3:
        return (
            "concept",
            MISTAKE_CATEGORIES["concept"],
            "先定位题目考查的核心概念，用一句话复述定义，再对照解析找出被混淆的两个概念并记录区别。",
        )

    return (
        "method",
        MISTAKE_CATEGORIES["method"],
        "对照解析拆解解题步骤，找出卡住的那一步，单独找 2 道只练这一步的题目，明天安排一次同类题巩固。",
    )


def difficulty_label(mastery: float) -> str:
    if mastery < 0.35:
        return "薄弱"
    if mastery < 0.7:
        return "待巩固"
    return "已掌握"


def pick_weak_points(items: List[dict], limit: int = 5) -> List[dict]:
    ordered = sorted(items, key=lambda item: (item.get("value", 0), -item.get("weight", 1)))
    return ordered[:limit]


def distribute_minutes(total: int, count: int) -> List[int]:
    """把每日可用时长平均分给 count 个任务，余数补给前几个任务。"""
    if count <= 0:
        return []
    base = total // count
    extra = total % count
    return [base + (1 if index < extra else 0) for index in range(count)]

# =========================================================
# v2.0 算法层（P0）：BKT-lite、遗忘曲线、收益密度、任务阶梯、反事实 Why
# 全部为纯函数，可复算；旧函数保留以兼容历史数据与对比。
# =========================================================

BKT_GUESS = {"choice": 0.25, "blank": 0.10, "short": 0.05}
BKT_SLIP = 0.15
BKT_LEARN = 0.08
MASTERY_MAX_STEP = 0.30
GAIN_ETA = {"study": 0.25, "practice": 0.18, "review": 0.10, "remedial": 0.28, "mock": 0.12}

# 证据权重 ω（v2.0 文档 5.1）：来源越可信，单次作答对掌握度的影响越大。
# 反脆弱挑战题 ω=0，由调用方跳过掌握度更新实现（答错不扣分，只记韧性）。
EVIDENCE_WEIGHT = {
    "quiz": 1.0,        # 随堂测
    "probe": 1.0,       # 主动探针
    "gap_verify": 1.0,  # 知识漏洞验证
    "self_test": 1.0,   # 知识点自测
    "mistake": 1.0,     # 错题录入
    "transfer": 1.2,    # 迁移压力测试：换情境作答，证据更强
    "flashcard": 0.5,   # 闪卡自评：主观判断，证据较弱
    "antifragile": 0.0,  # 反脆弱挑战：不计入掌握度
}


def evidence_weight_for(source: str) -> float:
    """按作答来源取证据权重，未知来源回退到 1.0。"""
    return EVIDENCE_WEIGHT.get(source, 1.0)


def bkt_update(
    old: float,
    correct: bool,
    question_type: str = "choice",
    evidence_weight: float = 1.0,
) -> float:
    """BKT-lite 掌握度更新：贝叶斯修正 + 学习转移 + 证据加权 + 防抖。"""
    guess = BKT_GUESS.get(question_type, 0.25)
    mastery = clamp(old)
    if correct:
        numerator = mastery * (1 - BKT_SLIP)
        denominator = numerator + (1 - mastery) * guess
    else:
        numerator = mastery * BKT_SLIP
        denominator = numerator + (1 - mastery) * (1 - guess)
    posterior = numerator / denominator if denominator > 1e-9 else mastery
    m_bkt = posterior + (1 - posterior) * BKT_LEARN
    m_new = mastery + evidence_weight * (m_bkt - mastery)
    m_new = clamp(m_new, mastery - MASTERY_MAX_STEP, mastery + MASTERY_MAX_STEP)
    return round(clamp(m_new), 4)


def mastery_confidence(effective_answers: float) -> float:
    """置信度 c = 1 - e^(-n_eff / 3)。"""
    return round(1 - math.exp(-max(effective_answers, 0.0) / 3), 3)


def mastery_uncertainty(mastery: float, effective_answers: float) -> float:
    """不确定性 u = sqrt(m(1-m) / (n_eff + 2))。"""
    m = clamp(mastery)
    return round(math.sqrt(m * (1 - m) / (max(effective_answers, 0.0) + 2)), 4)


def stability_for_stage(stage: int) -> float:
    """用复习档位近似记忆稳定度（天），迁移前不新增字段。"""
    index = max(0, min(int(stage), len(REVIEW_INTERVALS) - 1))
    return float(REVIEW_INTERVALS[index])


def retention(days: float, stability: float) -> float:
    """保持率 R(t) = 0.9^(t/S)。"""
    return round(0.9 ** (max(days, 0.0) / max(stability, 0.1)), 4)


def days_to_target(target: float, stability: float) -> int:
    """按目标保持率反推下次复习天数 t* = S·ln(r*)/ln(0.9)。"""
    if target <= 0 or target >= 1:
        return 0
    return max(0, round(max(stability, 0.1) * math.log(target) / math.log(0.9)))


def update_stability(stability: float, retention_now: float, correct: bool) -> float:
    """答对按已忘程度增加稳定度；答错回退到 0.4 倍并至少 1 天。"""
    current = max(stability, 0.1)
    if correct:
        return round(current * (1.7 + 2 * (1 - clamp(retention_now))), 2)
    return round(max(1.0, 0.4 * current), 2)


def task_tiers(minutes: int) -> dict:
    """任务弹性阶梯：标准 / 精简（约 50%）/ 最小（≤5 分钟）。"""
    standard = max(int(minutes), 1)
    lite = max(5, round(standard * 0.5))
    minimal = max(3, min(5, standard))
    return {"standard": standard, "lite": lite, "minimal": minimal}


def gate_for_prerequisites(prereq_masteries: Iterable[float], threshold: float = 0.5) -> float:
    """先修门控：存在掌握度低于阈值的先修知识点时降权。"""
    values = list(prereq_masteries)
    if any(value < threshold for value in values):
        return 0.5
    return 1.0


def value_density(
    weight: float,
    mastery: float,
    retention_now: float,
    uncertainty: float,
    days_left_count: int,
    gate: float = 1.0,
    minutes: int = 20,
    lambda_forget: float = 0.6,
    lambda_uncertainty: float = 0.3,
) -> dict:
    """收益密度 ρ = 价值 / 分钟；λ=0 且 gate=1 时退化为 v1.0 优先级。"""
    w = max(weight, 0.1)
    m = clamp(mastery)
    r = clamp(retention_now)
    u = max(uncertainty, 0.0)
    urgency = urgency_coefficient(days_left_count)
    value = w * ((1 - m) + lambda_forget * (1 - r) + lambda_uncertainty * u) * urgency * gate
    minutes = max(int(minutes), 1)
    return {
        "value": round(value, 4),
        "density": round(value / minutes, 6),
        "urgency": urgency,
        "gate": gate,
        "minutes": minutes,
    }


def expected_gain(weight: float, mastery: float, kind: str = "study", gate: float = 1.0) -> float:
    """考试日期望增益（百分制）：100 · w · η · (1-m) · G。"""
    eta = GAIN_ETA.get(kind, 0.18)
    return round(100 * max(weight, 0.1) * eta * (1 - clamp(mastery)) * gate, 2)


def task_why(
    weight: float,
    mastery: float,
    retention_now: float,
    uncertainty: float,
    days_left_count: int,
    kind: str = "study",
    minutes: int = 20,
    gate: float = 1.0,
    rank: int = 0,
    stability: float = 1.0,
) -> dict:
    """反事实 Why：给出价值、密度、期望增益，以及跳过/推迟/降档的可复算对照。"""
    density = value_density(
        weight, mastery, retention_now, uncertainty, days_left_count, gate, minutes
    )
    gain = expected_gain(weight, mastery, kind, gate)
    tiers = task_tiers(minutes)
    stability = max(float(stability or 1.0), 0.1)
    r_now = clamp(retention_now)
    r_delay = round(r_now * (0.9 ** (1.0 / stability)), 4)
    delayed = value_density(
        weight, mastery, r_delay, uncertainty, max(int(days_left_count) - 1, 0), gate, minutes
    )
    min_density = value_density(
        weight, mastery, retention_now, uncertainty, days_left_count, gate, tiers["minimal"]
    )
    w = round(weight, 3)
    m = round(clamp(mastery), 3)
    if_skipped = {
        "expected_gain": 0.0,
        "lost_gain": gain,
        "summary": (
            "如果今天跳过，将失去约 {gain} 分考试日期望增益"
            "（按 ΔE = 100×{w}×η×(1-{m})×{gate} 复算）。"
        ).format(gain=gain, w=w, m=m, gate=gate),
    }
    if_delayed = {
        "retention": r_delay,
        "value": delayed["value"],
        "density": delayed["density"],
        "summary": (
            "如果推迟 1 天，保持率将从 {now}% 降到 {later}%，"
            "任务价值从 {v0} 变为 {v1}（稳定度按 {s} 天、R(t)=0.9^(t/S) 复算）。"
        ).format(
            now=int(round(r_now * 100)),
            later=int(round(r_delay * 100)),
            v0=density["value"],
            v1=delayed["value"],
            s=round(stability, 1),
        ),
    }
    if_min_tier = {
        "minutes": tiers["minimal"],
        "value": min_density["value"],
        "density": min_density["density"],
        "expected_gain": gain,
        "summary": (
            "如果改做最小档 {mins} 分钟，收益密度从 {d0} 变为 {d1}；"
            "期望增益仍为 {gain} 分（ΔE 按掌握度计算，不随分钟缩放）。"
        ).format(
            mins=tiers["minimal"],
            d0=density["density"],
            d1=min_density["density"],
            gain=gain,
        ),
    }
    return {
        "weight": w,
        "mastery": m,
        "retention": round(r_now, 3),
        "uncertainty": round(max(uncertainty, 0.0), 4),
        "gate": gate,
        "value": density["value"],
        "density": density["density"],
        "expected_gain": gain,
        "minutes": minutes,
        "rank": rank,
        "stability": round(stability, 2),
        "tiers": tiers,
        "if_skipped": if_skipped,
        "if_delayed_1d": if_delayed,
        "if_min_tier": if_min_tier,
        "counterfactual": if_skipped["summary"] + if_delayed["summary"],
        "formula": "V = w·[(1-m)+0.6·(1-R)+0.3·u]·U(d)·G；ρ = V / 分钟；ΔE = 100·w·η·(1-m)·G；R(t)=0.9^(t/S)",
        "version": "rules-v2.1",
    }
