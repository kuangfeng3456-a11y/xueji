"""学情洞察：热力图、能力雷达、疲劳干预与成就徽章。"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FocusSession, Goal, KnowledgePoint, Mastery, Mistake, Task, Violation
from .rules import calc_streak, completion_rate, days_left

RADAR_LABELS = {
    "mastery": "知识掌握",
    "rhythm": "学习节奏",
    "focus": "专注投入",
    "accuracy": "纠错效率",
    "persistence": "持续坚持",
}


def _mastery_rows(db: Session, user_id: int, goal_id: int):
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    return points, rows


def _focus_sessions(db: Session, user_id: int, goal_id: int, since: date, today: date):
    start = datetime.combine(since, datetime.min.time())
    end = datetime.combine(today + timedelta(days=1), datetime.min.time())
    return db.scalars(
        select(FocusSession).where(
            FocusSession.user_id == user_id,
            FocusSession.goal_id == goal_id,
            FocusSession.started_at >= start,
            FocusSession.started_at < end,
        )
    ).all()


def build_heatmap(
    db: Session, user_id: int, goal_id: int, weeks: int = 12, today: Optional[date] = None
) -> List[Dict]:
    today = today or date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal_id,
            Task.day >= start,
            Task.day <= today,
        )
    ).all()
    sessions = _focus_sessions(db, user_id, goal_id, start, today)

    daily: Dict[date, Dict[str, int]] = defaultdict(lambda: {"minutes": 0, "done": 0, "focus": 0})
    for task in tasks:
        if task.status == "done":
            daily[task.day]["minutes"] += task.duration_min
            daily[task.day]["done"] += 1
    for session in sessions:
        if session.status == "completed":
            daily[(session.started_at + timedelta(hours=8)).date()]["focus"] += session.actual_minutes

    result = []
    cursor = start
    while cursor <= today:
        item = daily[cursor]
        minutes = item["minutes"]
        if minutes <= 0:
            level = 0
        elif minutes < 30:
            level = 1
        elif minutes < 60:
            level = 2
        elif minutes < 90:
            level = 3
        else:
            level = 4
        result.append(
            {
                "day": cursor,
                "minutes": minutes,
                "done": item["done"],
                "focus_minutes": item["focus"],
                "level": level,
            }
        )
        cursor += timedelta(days=1)
    return result


def build_radar(
    db: Session, user_id: int, goal_id: int, today: Optional[date] = None
) -> List[Dict]:
    today = today or date.today()
    points, mastery_rows = _mastery_rows(db, user_id, goal_id)
    avg_mastery = (
        round(sum(row.value for row in mastery_rows) / len(mastery_rows), 4) if mastery_rows else 0.0
    )

    since28 = today - timedelta(days=27)
    tasks_28 = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal_id,
            Task.day >= since28,
            Task.day <= today,
        )
    ).all()
    judged = [task for task in tasks_28 if task.status != "skipped"]
    rhythm = completion_rate(len([task for task in judged if task.status == "done"]), len(judged))

    since14 = today - timedelta(days=13)
    sessions = _focus_sessions(db, user_id, goal_id, since14, today)
    focus_days = {
        (session.started_at + timedelta(hours=8)).date()
        for session in sessions
        if session.status == "completed"
    }
    focus_value = min(1.0, len(focus_days) / 7)

    mistakes_14 = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user_id,
            Mistake.goal_id == goal_id,
            Mistake.created_at >= datetime.combine(since14, datetime.min.time()),
        )
    ).all()
    done_14 = len([task for task in judged if task.status == "done"])

    done_days = {
        task.day
        for task in db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal_id,
                Task.status == "done",
            )
        ).all()
    }
    streak = calc_streak(done_days, today)

    values = {
        "mastery": avg_mastery,
        "rhythm": rhythm,
        "focus": focus_value,
        "accuracy": max(0.0, 1 - min(1.0, len(mistakes_14) / max(1, done_14))),
        "persistence": min(1.0, streak / 14),
    }
    return [
        {"key": key, "label": RADAR_LABELS[key], "value": round(value, 4)}
        for key, value in values.items()
    ]


def build_fatigue(
    db: Session, user_id: int, goal_id: int, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    since3 = today - timedelta(days=2)
    sessions = _focus_sessions(db, user_id, goal_id, since3, today)
    focus_minutes = sum(session.actual_minutes for session in sessions if session.status == "completed")
    leaves = sum(session.leaves for session in sessions)
    aborted = len([session for session in sessions if session.status == "aborted"])

    since7 = today - timedelta(days=6)
    prev7_start = today - timedelta(days=13)
    recent_mistakes = len(
        db.scalars(
            select(Mistake).where(
                Mistake.user_id == user_id,
                Mistake.goal_id == goal_id,
                Mistake.created_at >= datetime.combine(since7, datetime.min.time()),
            )
        ).all()
    )
    previous_mistakes = len(
        db.scalars(
            select(Mistake).where(
                Mistake.user_id == user_id,
                Mistake.goal_id == goal_id,
                Mistake.created_at >= datetime.combine(prev7_start, datetime.min.time()),
                Mistake.created_at < datetime.combine(since7, datetime.min.time()),
            )
        ).all()
    )
    violations = db.scalars(
        select(Violation).where(
            Violation.user_id == user_id,
            Violation.goal_id == goal_id,
            Violation.day >= since7,
        )
    ).all()

    done_days = {
        task.day
        for task in db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal_id,
                Task.status == "done",
            )
        ).all()
    }
    streak = calc_streak(done_days, today)

    score = 0.0
    factors: List[str] = []
    if leaves > 0:
        score += leaves * 8
        factors.append(f"近 3 天离开专注页面 {leaves} 次")
    if aborted > 0:
        score += aborted * 14
        factors.append(f"近 3 天有 {aborted} 次专注中断")
    if focus_minutes > 180:
        score += min(20, (focus_minutes - 180) * 0.12)
        factors.append(f"近 3 天累计专注 {focus_minutes} 分钟，强度偏高")
    if recent_mistakes > previous_mistakes and recent_mistakes > 0:
        score += min(20, (recent_mistakes - previous_mistakes) * 6)
        factors.append(f"错题数从上周 {previous_mistakes} 道增至 {recent_mistakes} 道")
    if len(violations) >= 2:
        score += min(20, len(violations) * 5)
        factors.append(f"近 7 天有 {len(violations)} 次违约")
    if streak >= 10:
        score += min(10, (streak - 9) * 1.2)
        factors.append(f"已连续学习 {streak} 天，建议安排一次主动休息")

    score = int(min(100, round(score)))
    if score >= 60:
        level = "high"
        advice = "疲劳指数偏高：建议今天只保留 1 个最重要任务，其余自动顺延，先恢复状态。"
        suggested = 1
    elif score >= 30:
        level = "medium"
        advice = "疲劳开始累积：建议把今日任务降到 2 个，优先复习，避免硬撑。"
        suggested = 2
    else:
        level = "low"
        advice = "状态良好：保持当前节奏，专注与纠错都在健康区间。"
        suggested = 3

    return {
        "score": score,
        "level": level,
        "factors": factors or ["暂无明显疲劳信号"],
        "advice": advice,
        "suggested_tasks_per_day": suggested,
    }


def build_achievements(
    db: Session, user_id: int, goal_id: int, today: Optional[date] = None
) -> List[Dict]:
    today = today or date.today()
    tasks = db.scalars(
        select(Task).where(Task.user_id == user_id, Task.goal_id == goal_id)
    ).all()
    done_tasks = [task for task in tasks if task.status == "done"]
    points, mastery_rows = _mastery_rows(db, user_id, goal_id)
    avg_mastery = (
        sum(row.value for row in mastery_rows) / len(mastery_rows) if mastery_rows else 0.0
    )

    done_days = {task.day for task in done_tasks}
    streak = calc_streak(done_days, today)

    sessions = db.scalars(
        select(FocusSession).where(
            FocusSession.user_id == user_id,
            FocusSession.goal_id == goal_id,
            FocusSession.status == "completed",
        )
    ).all()
    focus_count = len(sessions)

    by_day: Dict[date, List[Task]] = defaultdict(list)
    for task in tasks:
        if task.status != "skipped":
            by_day[task.day].append(task)
    perfect_days = len(
        [
            day
            for day, items in by_day.items()
            if items and all(item.status == "done" for item in items)
        ]
    )

    week_start = today - timedelta(days=6)
    week_violations = len(
        db.scalars(
            select(Violation).where(
                Violation.user_id == user_id,
                Violation.goal_id == goal_id,
                Violation.day >= week_start,
            )
        ).all()
    )

    def badge(code, name, description, progress, target, unit="") -> Dict:
        return {
            "code": code,
            "name": name,
            "description": description,
            "unlocked": progress >= target,
            "progress": min(progress, target),
            "target": target,
            "unit": unit,
        }

    return [
        badge("first_task", "第一步", "完成第一个学习任务", len(done_tasks), 1, "个任务"),
        badge("streak_7", "七日不断", "连续打卡 7 天", streak, 7, "天"),
        badge("streak_15", "半月坚持", "连续打卡 15 天", streak, 15, "天"),
        badge("tasks_50", "积少成多", "累计完成 50 个任务", len(done_tasks), 50, "个任务"),
        badge("mastery_60", "半程掌握", "平均掌握度达到 60%", int(avg_mastery * 100), 60, "%"),
        badge("focus_5", "专注新手", "完成 5 次强制专注", focus_count, 5, "次"),
        badge("perfect_3", "满勤三天", "3 天完成全部任务", perfect_days, 3, "天"),
        badge("clear_week", "自律一周", "近 7 天零违约", 0 if week_violations else 1, 1, "周"),
    ]


def build_insights(
    db: Session, user_id: int, goal_id: int, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    heatmap = build_heatmap(db, user_id, goal_id, today=today)
    radar = build_radar(db, user_id, goal_id, today=today)
    fatigue = build_fatigue(db, user_id, goal_id, today=today)
    achievements = build_achievements(db, user_id, goal_id, today=today)

    done_days = {
        task.day
        for task in db.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.goal_id == goal_id,
                Task.status == "done",
            )
        ).all()
    }
    return {
        "heatmap": heatmap,
        "radar": radar,
        "radar_score": round(sum(item["value"] for item in radar) / len(radar), 4),
        "fatigue": fatigue,
        "achievements": achievements,
        "streak": calc_streak(done_days, today),
        "total_minutes": sum(item["minutes"] for item in heatmap),
        "active_days": len([item for item in heatmap if item["minutes"] > 0]),
    }