"""语音问答：规则优先的教练问答，可选大模型润色。"""

from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import Goal, KnowledgePoint, Mastery, Mistake, Task, User
from .rules import days_left


def _today_tasks(db: Session, user_id: int, goal_id: int, today: date):
    return db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.goal_id == goal_id,
            Task.day == today,
            Task.status != "skipped",
        ).order_by(Task.priority.desc())
    ).all()


def _mastery_items(db: Session, user_id: int, goal_id: int):
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = (
        db.scalars(
            select(Mastery).where(
                Mastery.user_id == user_id,
                Mastery.kp_id.in_([point.id for point in points] or [0]),
            )
        ).all()
        if points
        else []
    )
    point_map = {point.id: point.name for point in points}
    items = [
        {"name": point_map.get(row.kp_id, ""), "value": row.value}
        for row in rows
        if point_map.get(row.kp_id)
    ]
    items.sort(key=lambda item: item["value"])
    return items


def build_rule_answer(
    db: Session, user: User, goal: Optional[Goal], question: str, today: Optional[date] = None
) -> Tuple[str, list]:
    today = today or date.today()
    question = (question or "").strip()
    if not goal:
        return (
            "你还没有设置考试目标。先到「目标与资料」填写考试名称、考试日期和每天可用时间，"
            "我才能给出针对性的学习建议。",
            ["创建考试目标", "导入学习资料"],
        )

    remain = days_left(goal.exam_date, today)
    tasks = _today_tasks(db, user.id, goal.id, today)
    pending = [task for task in tasks if task.status == "pending"]
    mastery_items = _mastery_items(db, user.id, goal.id)
    weakest = mastery_items[:3]
    since = datetime.combine(today - timedelta(days=7), datetime.min.time())
    mistakes = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= since,
        )
    ).all()

    def has(*words: str) -> bool:
        return any(word in question for word in words)

    if has("几天", "倒计时", "还有多久", "什么时候考"):
        return (
            f"距离「{goal.exam_name}」还有 {remain} 天，每天可用 {goal.daily_minutes} 分钟。"
            f"按当前节奏，建议优先完成带「复习」标签的任务。",
            ["查看学习计划", "生成周报"],
        )

    if has("薄弱", "弱项", "哪里差", "最差", "短板"):
        if not weakest:
            return ("还没有掌握度数据。先导入知识点并完成几次自测，我就能找出你的薄弱点。", ["导入资料"])
        names = "、".join(f"{item['name']}（{item['value'] * 100:.0f}%）" for item in weakest)
        return (
            f"当前最薄弱的三个知识点是：{names}。建议今天先安排 20 分钟基础回顾，"
            "明天做 2 道同类题确认是否补上。",
            [f"复习 {weakest[0]['name']}", "录入错题"],
        )

    if has("今天", "学什么", "干什么", "任务", "安排"):
        if not tasks:
            return (
                f"今天还没有排任务。去「学习计划」生成计划，我会按知识点权重、掌握度和剩余 {remain} 天自动排入。",
                ["生成 7 天计划"],
            )
        lines = "；".join(
            f"{task.title}（{task.duration_min} 分钟，{task.status == 'done' and '已完成' or '待完成'}）"
            for task in tasks[:5]
        )
        return (
            f"今天共 {len(tasks)} 个任务，还剩 {len(pending)} 个待完成，约 "
            f"{sum(task.duration_min for task in pending)} 分钟。{lines}。",
            ["去打卡", "查看任务理由"],
        )

    if has("复习", "遗忘", "间隔"):
        return (
            "复习按 1 / 2 / 4 / 7 / 15 天的间隔安排，答错会回到 1 天重新开始。"
            "今天优先复习到期且掌握度低于 0.5 的知识点，效果最好。",
            ["查看掌握度", "生成计划"],
        )

    if has("错题", "错因", "为什么错"):
        if not mistakes:
            return ("近 7 天还没有错题记录。做错的题及时录入，我会按四类错因给出补救建议。", ["录入错题"])
        stats = {}
        for mistake in mistakes:
            stats[mistake.category_label] = stats.get(mistake.category_label, 0) + 1
        detail = "、".join(f"{label} {count} 道" for label, count in stats.items())
        return (
            f"近 7 天共 {len(mistakes)} 道错题：{detail}。"
            "「方法不会」优先看解题步骤，「概念不清」优先重读定义，「粗心」做检查清单。",
            ["查看错题本", "插入补救任务"],
        )

    if has("计划", "排期", "来得及"):
        return (
            f"当前目标是「{goal.exam_name}」，还剩 {remain} 天，每天 {goal.daily_minutes} 分钟。"
            "计划由优先级公式排程，落后会自动顺延，错题增多会自动插入补救任务，不会因为一次落后就作废。",
            ["生成计划", "智能重排"],
        )

    if has("坚持", "拖延", "不想学", "累", "焦虑"):
        return (
            "先从最小的任务开始，告诉自己只做 10 分钟。启动比完美更重要。"
            "如果连续落后，系统会把每日任务从 3 个降到 2 个，先把节奏稳住。",
            ["查看学习节奏", "调整每日时长"],
        )

    return (
        f"我可以帮你查今天学什么、薄弱知识点、剩余天数、复习安排和错题分析。"
        f"当前「{goal.exam_name}」还剩 {remain} 天，今天有 {len(pending)} 个待完成任务。",
        ["今天学什么", "我的薄弱点", "还剩几天"],
    )


async def answer_question(
    db: Session, user: User, goal: Optional[Goal], question: str, today: Optional[date] = None
) -> dict:
    answer, suggestions = build_rule_answer(db, user, goal, question, today)
    source = "rule"
    if llm.available and goal:
        system = (
            "你是学迹学习教练。请基于给定事实回答用户问题，80 字以内，"
            "保留所有数字，不得编造不存在的任务或数据，语气耐心、具体、可执行。只输出中文回答。"
        )
        prompt = f"用户问题：{question}\n可用事实：{answer}"
        text = await llm.chat(system, prompt, temperature=0.4, max_tokens=300)
        if text:
            answer = text.strip()
            source = "llm"
    return {"answer": answer, "source": source, "suggestions": suggestions}


_FOLLOWUP_CUES = ("为什么", "为何", "然后", "继续", "详细", "具体", "展开", "什么意思", "怎么做", "再说", "接着")


def is_followup(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    if text in ("为什么", "为何", "然后呢", "继续", "展开", "具体一点", "怎么做", "再说一遍", "接着说"):
        return True
    return len(text) <= 16 and any(cue in text for cue in _FOLLOWUP_CUES)


def rule_answer_with_history(
    db: Session,
    user: User,
    goal: Optional[Goal],
    question: str,
    history: Optional[list] = None,
    today: Optional[date] = None,
) -> dict:
    """把追问接回上一问的事实，避免连续对话丢失上下文。"""
    prior = [item for item in (history or []) if str(item.get("text") or "").strip()]
    base_question = (question or "").strip()
    follow = False
    if is_followup(base_question) and prior:
        last_user = ""
        for item in reversed(prior):
            if item.get("role") == "user" and str(item.get("text") or "").strip():
                last_user = str(item["text"]).strip()
                break
        if last_user:
            follow = True
            base_question = last_user
    answer, suggestions = build_rule_answer(db, user, goal, base_question, today)
    if follow:
        answer = f"接着上一问「{base_question}」：{answer}"
    return {
        "answer": answer,
        "source": "rule",
        "suggestions": suggestions[:4],
        "followup": follow,
    }


async def answer_with_history(
    db: Session,
    user: User,
    goal: Optional[Goal],
    question: str,
    history: Optional[list] = None,
    today: Optional[date] = None,
) -> dict:
    ruled = rule_answer_with_history(db, user, goal, question, history, today)
    answer = ruled["answer"]
    source = "rule"
    if llm.available and goal:
        lines = []
        for item in (history or [])[-8:]:
            who = "学生" if item.get("role") == "user" else "教练"
            lines.append(f"{who}：{str(item.get('text') or '')[:200]}")
        system = (
            "你是学迹学习教练。请基于给定事实和对话记录回答，80 字以内，"
            "保留所有数字，不得编造不存在的任务或数据，语气耐心、具体、可执行。只输出中文回答。"
        )
        prompt = (
            "对话记录：\n"
            + ("\n".join(lines) if lines else "（没有更早的对话）")
            + f"\n当前问题：{question}\n可用事实：{answer}"
        )
        text = await llm.chat(system, prompt, temperature=0.4, max_tokens=300)
        if text:
            answer = text.strip()
            source = "llm"
    ruled["answer"] = answer
    ruled["source"] = source
    return ruled