"""C3 实施意图微承诺（文档 4.4 / 3.2）。

「如果—那么」式实施意图（implementation intention）是行为科学里成本最低的
执行干预：把「我要学」改写成「如果出现某情境，那么我就做某个具体动作」，
显著提高执行率。产品闭环：

1. 教练基于今日任务与用户常学时段生成候选承诺（规则生成，不依赖模型）；
2. 用户一键采纳或自建；
3. 当日打卡履行；过期未确认的承诺在下次访问时惰性结算为 missed；
4. 沉淀习惯数据：履行率、承诺履行与当日任务完成率的相关性。

原则：规则管事实，模型管表达 —— 承诺文本全部来自可复算的规则模板。
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import Commitment, Goal, Task

MAX_ACTIVE = 5  # 同时挂着的承诺上限：微承诺贵精不贵多


# ---------------------------------------------------------------------------
# 教练生成候选承诺（规则模板，全部可复算）
# ---------------------------------------------------------------------------

def _context_slots(goal: Goal) -> List[str]:
    """按每日容量给出时间情境候选，峰值时段优先（文档 5.6/5.3 的口径）。"""
    minutes = max(30, int(goal.daily_minutes or 60))
    if minutes >= 180:
        return ["早上", "午休结束时", "晚饭后", "睡前一小时"]
    if minutes >= 90:
        return ["早上", "午休结束时", "晚饭后"]
    return ["早上", "晚饭后"]


def _templates_for(task: Task, goal: Goal) -> List[Dict[str, str]]:
    """为一个任务生成 2 条「如果—那么」候选：开工情境 + 抗打断情境。"""
    title = (task.title or "今日任务").strip()
    min_version = f"「{title}」的 5 分钟最小版"
    return [
        {
            "if_condition": f"如果现在是{_context_slots(goal)[0]}、我坐到了书桌前",
            "then_action": f"那么我先做{min_version}，做完才算坐下",
            "task_id": task.id,
        },
        {
            "if_condition": "如果中途想刷手机或者想放弃",
            "then_action": f"那么我只做{min_version}，做完允许自己休息 5 分钟",
            "task_id": task.id,
        },
    ]


def generate_suggestions(db: Session, goal: Goal, day: date, limit: int = 3) -> List[Dict]:
    """基于今日最该做的任务（优先级最高且未完成）生成候选承诺。

    排序规则可复算：任务 priority 降序 → duration 升序（先承诺小的）。
    """
    tasks = (
        db.query(Task)
        .filter(
            Task.goal_id == goal.id,
            Task.day == day,
            Task.status.in_(["pending", "doing"]),
        )
        .order_by(Task.priority.desc(), Task.duration_min.asc())
        .limit(3)
        .all()
    )
    suggestions: List[Dict] = []
    seen_pairs = set()
    for task in tasks:
        for tpl in _templates_for(task, goal):
            key = (tpl["if_condition"], tpl["then_action"])
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            suggestions.append(
                {
                    "task_id": tpl["task_id"],
                    "task_title": task.title,
                    "if_condition": tpl["if_condition"],
                    "then_action": tpl["then_action"],
                }
            )
            if len(suggestions) >= limit:
                return suggestions
    return suggestions


# ---------------------------------------------------------------------------
# 惰性结算：过期未确认 → missed
# ---------------------------------------------------------------------------

def settle_overdue(db: Session, user_id: int, goal_id: Optional[int] = None) -> int:
    """把昨天及更早、仍处于 pending 的承诺结算为 missed（幂等）。"""
    today = date.today()
    query = db.query(Commitment).filter(
        Commitment.user_id == user_id,
        Commitment.status == "pending",
        Commitment.due_date < today,
    )
    if goal_id:
        query = query.filter(Commitment.goal_id == goal_id)
    overdue = query.all()
    now = datetime.utcnow()
    for item in overdue:
        item.status = "missed"
        item.settled_at = now
    if overdue:
        db.commit()
    return len(overdue)


# ---------------------------------------------------------------------------
# 统计：履行率 + 承诺履行与当日完成率的相关性
# ---------------------------------------------------------------------------

def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    """皮尔逊相关系数；样本不足（<3）或零方差时返回 None，不硬凑数字。"""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return round(cov / (vx * vy) ** 0.5, 3)


def stats(db: Session, user_id: int, goal_id: int, window_days: int = 28) -> Dict:
    """履行率与「承诺日 vs 当日任务完成率」的相关性（文档 C3 指标口径）。"""
    since = date.today() - timedelta(days=window_days - 1)
    rows = (
        db.query(Commitment)
        .filter(
            Commitment.user_id == user_id,
            Commitment.goal_id == goal_id,
            Commitment.status.in_(["fulfilled", "missed"]),
            Commitment.due_date >= since,
        )
        .all()
    )
    fulfilled = len([r for r in rows if r.status == "fulfilled"])
    missed = len(rows) - fulfilled
    rate = round(fulfilled / len(rows), 3) if rows else None

    # 按承诺到期日聚合当日任务完成率，计算相关性
    days = sorted({r.due_date for r in rows})
    xs: List[float] = []
    ys: List[float] = []
    for day in days:
        day_rows = [r for r in rows if r.due_date == day]
        day_fulfilled = len([r for r in day_rows if r.status == "fulfilled"]) / len(day_rows)
        total = (
            db.query(func.count(Task.id))
            .filter(Task.goal_id == goal_id, Task.day == day)
            .scalar()
            or 0
        )
        done = (
            db.query(func.count(Task.id))
            .filter(Task.goal_id == goal_id, Task.day == day, Task.status == "done")
            .scalar()
            or 0
        )
        if total:
            xs.append(day_fulfilled)
            ys.append(done / total)

    correlation = _pearson(xs, ys)
    return {
        "window_days": window_days,
        "fulfilled": fulfilled,
        "missed": missed,
        "fulfillment_rate": rate,
        "correlation": correlation,  # 承诺履行率 与 当日任务完成率 的皮尔逊 r
        "sample_days": len(xs),
    }


# ---------------------------------------------------------------------------
# 今日列表
# ---------------------------------------------------------------------------

def today_list(db: Session, user_id: int, goal_id: int, day: date) -> Dict:
    settle_overdue(db, user_id, goal_id)
    items = (
        db.query(Commitment)
        .filter(
            Commitment.user_id == user_id,
            Commitment.goal_id == goal_id,
            or_(Commitment.due_date == day, Commitment.status == "pending"),
        )
        .order_by(Commitment.status.asc(), Commitment.created_at.asc())
        .limit(20)
        .all()
    )
    active_count = (
        db.query(func.count(Commitment.id))
        .filter(
            Commitment.user_id == user_id,
            Commitment.goal_id == goal_id,
            Commitment.status == "pending",
        )
        .scalar()
        or 0
    )
    return {
        "date": day.isoformat(),
        "items": [_serialize(item) for item in items],
        "active_count": int(active_count),
        "max_active": MAX_ACTIVE,
    }


def _serialize(item: Commitment) -> Dict:
    return {
        "id": item.id,
        "task_id": item.task_id,
        "if_condition": item.if_condition,
        "then_action": item.then_action,
        "due_date": item.due_date.isoformat(),
        "status": item.status,
        "source": item.source,
        "checkin_note": item.checkin_note,
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }
