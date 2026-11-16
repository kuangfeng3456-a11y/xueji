from typing import List, Optional

from ..llm import llm
from ..models import Goal, Task, User


def _rule_message(
    user: User,
    goal: Optional[Goal],
    tasks: List[Task],
    streak: int,
    mistakes_7d: int,
    remain: int,
) -> str:
    name = user.nickname or user.username
    pending = [task for task in tasks if task.status == "pending"]
    done = [task for task in tasks if task.status == "done"]
    overdue = [task for task in pending if goal is not None and task.day < goal.created_at.date()]

    if not goal:
        return f"{name}，先设定一个考试目标吧，我会据此排出每天该学什么。"
    if not tasks:
        return f"{name}，今天还没有任务，点一下「生成计划」我就把今天的学习安排排好。"
    if overdue:
        return (
            f"{name}，有 {len(overdue)} 个任务落后了。别急，先花 20 分钟补上优先级最高的那个，"
            "其余我会自动顺延，不会让计划作废。"
        )
    if not pending:
        return (
            f"{name}，今天 {len(done)} 个任务全部完成，连续打卡 {streak} 天。"
            f"距考试还有 {remain} 天，保持这个节奏就很稳。"
        )
    total = sum(task.duration_min for task in pending)
    tip = ""
    if mistakes_7d >= 3:
        tip = f"近 7 天有 {mistakes_7d} 道错题，做完今天的任务后，优先看错因归类为「方法不会」的那几道。"
    elif remain <= 7:
        tip = "进入冲刺期，复习任务优先于新内容，先保住已掌握的知识点。"
    else:
        tip = "先做最短的那个任务，启动比完美更重要。"
    return f"{name}，今天还剩 {len(pending)} 个任务、约 {total} 分钟。{tip}"


async def coach_message(
    user: User,
    goal: Optional[Goal],
    tasks: List[Task],
    streak: int,
    mistakes_7d: int,
    remain: int,
    use_llm: bool = True,
) -> str:
    base = _rule_message(user, goal, tasks, streak, mistakes_7d, remain)
    if use_llm and llm.available and goal:
        system = (
            "你是学习教练，语气像耐心的学长。请基于给定事实写 80 字以内的当日提醒，"
            "保留关键数字，不要编造事实；末尾必须附一条「如果——那么——」的实施意图微承诺，"
            "只输出中文正文。"
        )
        prompt = (
            f"用户昵称：{user.nickname}；考试：{goal.exam_name}；剩余 {remain} 天；"
            f"连续打卡 {streak} 天；今日任务 {len(tasks)} 个；近 7 天错题 {mistakes_7d} 道。"
            f"规则生成的原话：{base}"
        )
        text = await llm.chat(system, prompt, temperature=0.5, max_tokens=300)
        if text:
            return text.strip()
    return base