"""Reporter Agent 的确定性内核：周报复盘。"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, MasteryHistory, Mistake, Report, Task, User
from ..llm import llm
from .rules import MISTAKE_CATEGORIES, completion_rate, days_left, week_bounds


def _snapshot_value(db: Session, user_id: int, kp_id: int, before: date) -> Optional[float]:
    row = db.scalar(
        select(MasteryHistory)
        .where(
            MasteryHistory.user_id == user_id,
            MasteryHistory.kp_id == kp_id,
            MasteryHistory.day <= before,
        )
        .order_by(MasteryHistory.day.desc())
    )
    return row.value if row else None


def _rule_content(
    goal: Goal,
    week_start: date,
    week_end: date,
    tasks: List[Task],
    rate: float,
    done_minutes: int,
    delta: float,
    weak: List[str],
    mistake_stats: dict,
    total_mistakes: int,
    remain: int,
) -> str:
    done = sum(1 for task in tasks if task.status == "done")
    total = len(tasks)
    mistake_line = "；".join(
        f"{MISTAKE_CATEGORIES.get(key, key)} {value} 道" for key, value in mistake_stats.items() if value
    ) or "暂无错题记录"
    weak_line = "、".join(weak) if weak else "暂无明显薄弱点"
    trend = "上升" if delta > 0.01 else ("下降" if delta < -0.01 else "基本持平")
    suggestion = (
        f"下周优先补「{weak[0]}」，每天安排 20 分钟基础回顾 + 10 分钟同类题。"
        if weak
        else "保持当前节奏，适当增加综合练习。"
    )
    return (
        f"【本周概览】{week_start.isoformat()} 至 {week_end.isoformat()}，"
        f"完成 {done}/{total} 个任务，完成率 {rate * 100:.0f}%，累计学习 {done_minutes} 分钟。\n"
        f"【掌握度变化】平均掌握度较周初{trend} {abs(delta):.2f}，当前薄弱点：{weak_line}。\n"
        f"【错题分析】本周记录 {total_mistakes} 道错题：{mistake_line}。\n"
        f"【下周建议】{suggestion}距「{goal.exam_name}」还剩 {remain} 天，"
        f"建议保持每天 {goal.daily_minutes} 分钟，优先完成带复习标签的任务。"
    )


def build_weekly_report(
    db: Session,
    user: User,
    goal: Goal,
    week_start: Optional[date] = None,
) -> Report:
    if week_start is None:
        week_start, week_end = week_bounds(date.today())
    else:
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6)

    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day >= week_start,
            Task.day <= week_end,
        )
    ).all()
    done_tasks = [task for task in tasks if task.status == "done"]
    rate = completion_rate(len(done_tasks), len(tasks))
    done_minutes = sum(task.duration_min for task in done_tasks)

    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    deltas: List[float] = []
    mastery_rows: List[dict] = []
    for point in points:
        record = db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id))
        current = record.value if record else 0.0
        baseline = _snapshot_value(db, user.id, point.id, week_start)
        if baseline is None:
            baseline = current
        deltas.append(current - baseline)
        mastery_rows.append({"name": point.name, "value": current, "weight": point.weight})
    mastery_delta = round(sum(deltas) / len(deltas), 4) if deltas else 0.0
    weak = [item["name"] for item in sorted(mastery_rows, key=lambda row: row["value"])[:3]]

    mistakes = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= datetime.combine(week_start, datetime.min.time()),
            Mistake.created_at <= datetime.combine(week_end, datetime.max.time()),
        )
    ).all()
    mistake_stats: dict = {}
    for mistake in mistakes:
        mistake_stats[mistake.category] = mistake_stats.get(mistake.category, 0) + 1

    remain = days_left(goal.exam_date)
    content = _rule_content(
        goal,
        week_start,
        week_end,
        tasks,
        rate,
        done_minutes,
        mastery_delta,
        weak,
        mistake_stats,
        len(mistakes),
        remain,
    )
    focus = weak[0] if weak else "保持节奏"


    report = db.scalar(
        select(Report).where(
            Report.user_id == user.id,
            Report.goal_id == goal.id,
            Report.week_start == week_start,
        )
    )
    if report is None:
        report = Report(
            user_id=user.id,
            goal_id=goal.id,
            week_start=week_start,
            week_end=week_end,
            completion_rate=rate,
            mastery_delta=mastery_delta,
            focus=focus,
            content=content,
        )
        db.add(report)
    else:
        report.week_end = week_end
        report.completion_rate = rate
        report.mastery_delta = mastery_delta
        report.focus = focus
        report.content = content
    db.commit()
    db.refresh(report)
    return report

async def generate_weekly_report(
    db: Session,
    user: User,
    goal: Goal,
    week_start: Optional[date] = None,
    use_llm: bool = True,
) -> Report:
    report = build_weekly_report(db, user, goal, week_start=week_start)
    if use_llm and llm.available:
        system = (
            "你是学习教练，请基于给定的周报写一段 120 字以内的点评。"
            "必须保留所有数字，语气具体、克制、可执行。只输出中文点评正文。"
        )
        prompt = (
            f"考试：{goal.exam_name}；完成率 {report.completion_rate * 100:.0f}%；"
            f"掌握度变化 {report.mastery_delta:+.2f}；下周重点：{report.focus}。"
            f"原始周报：{report.content}"
        )
        extra = await llm.chat(system, prompt, temperature=0.4, max_tokens=400)
        if extra:
            report.content = report.content + "\n【教练点评】" + extra.strip()
            db.commit()
            db.refresh(report)
    return report