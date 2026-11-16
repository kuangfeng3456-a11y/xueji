from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Goal, Report, User
from ..services.reporting import generate_weekly_report


async def reporter_generate(
    db: Session,
    user: User,
    goal: Goal,
    week_start: Optional[date] = None,
    use_llm: bool = True,
) -> Report:
    return await generate_weekly_report(db, user, goal, week_start=week_start, use_llm=use_llm)