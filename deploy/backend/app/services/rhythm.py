"""双维度学习画像的第二个维度：学习节奏。

「掌握度」回答“你会什么”，「学习节奏」回答“你怎么学”：常学时段、拖延规律、
近期完成率。这里全部由程序统计完成，不依赖大模型，保证结果稳定可复现。
"""

from collections import Counter
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Task
from .rules import completion_rate

WINDOW_DAYS = 28
MIN_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 60
DEFAULT_TASKS_PER_DAY = 3
REDUCED_TASKS_PER_DAY = 2
MIN_SAMPLES_FOR_ADAPTION = 6
MIN_DELAY_SAMPLES = 3
PROCRASTINATION_DAYS = 2

PERIODS = [
    ("morning", "上午"),
    ("afternoon", "下午"),
    ("evening", "晚上"),
    ("night", "深夜"),
]
PERIOD_LABELS = dict(PERIODS)


def hour_to_period(hour: int) -> str:
    """把打卡小时映射到常学时段。"""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _habit_label(peak_label: Optional[str], avg_delay: float, rate: float, samples: int) -> str:
    if not peak_label or samples == 0:
        return "节奏待建立"
    if avg_delay >= PROCRASTINATION_DAYS:
        return f"{peak_label}型 · 拖延明显"
    if rate >= 0.8:
        return f"{peak_label}型 · 节奏稳定"
    return f"{peak_label}型"


def _suggestion(
    days: int,
    samples: int,
    rate: float,
    avg_delay: float,
    peak_label: Optional[str],
    tasks_per_day: int,
) -> str:
    if samples == 0:
        return "还没有足够的打卡数据，坚持记录 3 天后就能看到你的学习节奏。"
    if tasks_per_day < DEFAULT_TASKS_PER_DAY:
        return (
            f"最近 {days} 天完成率 {rate * 100:.0f}%，系统已把每日任务从 "
            f"{DEFAULT_TASKS_PER_DAY} 个下调为 {tasks_per_day} 个，先把节奏稳住。"
        )
    if peak_label and avg_delay < 1:
        return f"你习惯在{peak_label}学习，建议把最重要的任务固定在这个时段。"
    if avg_delay >= PROCRASTINATION_DAYS:
        return f"平均比计划晚 {avg_delay:.1f} 天完成，建议把计划时长下调 20%，先保证当天完成。"
    return "保持每天固定时间打卡，能进一步稳定你的学习节奏。"


def build_rhythm(
    db: Session,
    user_id: int,
    goal_id: int,
    today: Optional[date] = None,
    days: int = WINDOW_DAYS,
) -> Dict:
    """统计最近 N 天的任务行为，输出节奏画像与建议的每日任务数。"""
    today = today or date.today()
    days = max(MIN_WINDOW_DAYS, min(days, MAX_WINDOW_DAYS))
    window_start = today - timedelta(days=days - 1)

    rows: List[Task] = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal_id,
            Task.day >= window_start,
            Task.day <= today,
        )
    ).all()

    skipped = [task for task in rows if task.status == "skipped"]
    judged = [task for task in rows if task.status != "skipped"]
    done = [task for task in judged if task.status == "done"]
    pending = [task for task in judged if task.status == "pending"]

    delays: List[int] = []
    period_counter: Counter = Counter()
    for task in done:
        if task.done_at is None:
            continue
        delays.append(max((task.done_at.date() - task.day).days, 0))
        period_counter[hour_to_period(task.done_at.hour)] += 1

    rate = completion_rate(len(done), len(judged))
    done_minutes = sum(task.duration_min for task in done)
    avg_delay = round(sum(delays) / len(delays), 2) if delays else 0.0
    on_time_rate = round(sum(1 for delay in delays if delay <= 0) / len(delays), 4) if delays else 0.0
    skip_rate = completion_rate(len(skipped), len(rows))

    peak_code: Optional[str] = None
    if period_counter:
        code, count = period_counter.most_common(1)[0]
        peak_code = code if count >= 2 else None
    peak_label = PERIOD_LABELS.get(peak_code) if peak_code else None

    tasks_per_day = DEFAULT_TASKS_PER_DAY
    if len(judged) >= MIN_SAMPLES_FOR_ADAPTION and rate < 0.5:
        tasks_per_day = REDUCED_TASKS_PER_DAY
    elif len(delays) >= MIN_DELAY_SAMPLES and avg_delay >= PROCRASTINATION_DAYS:
        tasks_per_day = REDUCED_TASKS_PER_DAY

    overdue_pending = sum(1 for task in pending if task.day < today)

    return {
        "window_days": days,
        "sampled_tasks": len(rows),
        "completion_rate": rate,
        "done_minutes": done_minutes,
        "avg_delay_days": avg_delay,
        "on_time_rate": on_time_rate,
        "skip_rate": skip_rate,
        "overdue_pending": overdue_pending,
        "peak_period": peak_code,
        "peak_period_label": peak_label,
        "periods": [
            {"code": code, "label": label, "count": period_counter.get(code, 0)}
            for code, label in PERIODS
        ],
        "habit": _habit_label(peak_label, avg_delay, rate, len(judged)),
        "tasks_per_day": tasks_per_day,
        "suggestion": _suggestion(days, len(judged), rate, avg_delay, peak_label, tasks_per_day),
    }