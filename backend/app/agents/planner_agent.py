from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from ..llm import llm
from ..models import Goal, User
from ..services.planner import build_plan, replan
from ..services.rules import days_left


async def planner_generate(
    db: Session,
    user_id: int,
    goal: Goal,
    days: int = 7,
    regenerate: bool = False,
    today: Optional[date] = None,
) -> dict:
    result = build_plan(db, user_id, goal, days=days, regenerate=regenerate, today=today)
    if llm.available and result["tasks"]:
        samples = "；".join(task["title"] for task in result["tasks"][:5])
        system = (
            "你是学习计划教练。请基于给定的规则排程结果，写一句不超过 70 字的今日重点，"
            "必须保留剩余天数和任务数量，不得改变任务安排，不得编造任务。只输出中文。"
        )
        prompt = (
            f"考试：{goal.exam_name}；剩余 {days_left(goal.exam_date, today)} 天；"
            f"本次生成 {len(result['tasks'])} 个任务；示例：{samples}；规则摘要：{result['summary']}"
        )
        text = await llm.chat(system, prompt, temperature=0.4, max_tokens=220)
        if text:
            result["summary"] = text.strip() + " " + result["summary"]
    return result


async def planner_replan(
    db: Session,
    user_id: int,
    goal: Goal,
    trigger: str = "manual",
    today: Optional[date] = None,
) -> dict:
    return replan(db, user_id, goal, trigger=trigger, today=today)