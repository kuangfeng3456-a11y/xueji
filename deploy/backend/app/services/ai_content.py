"""把学情洞察、冲刺策略与闪卡释义统一接到 DeepSeek，失败时回退规则文案。"""

from datetime import date
from typing import Dict, Optional

from ..cache import cache
from ..llm import llm
from ..models import Goal, KnowledgePoint, User
from . import knowledge_base


def _rule_insight(insights: Dict) -> str:
    radar = "、".join(
        f"{item['label']}{round(item['value'] * 100)}%" for item in insights.get("radar", [])
    )
    fatigue = insights.get("fatigue", {})
    return (
        f"近 12 周有 {insights.get('active_days', 0)} 天学习记录，累计 "
        f"{round(insights.get('total_minutes', 0) / 60)} 小时。能力结构：{radar}。"
        f"当前疲劳指数 {fatigue.get('score', 0)}，{fatigue.get('advice', '')}"
    )


async def ai_insight_report(
    db, user: User, goal: Goal, insights: Dict, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    fallback = {"text": _rule_insight(insights), "engine": "rule"}
    if not llm.available:
        return fallback

    key = (
        f"ai:insights:{user.id}:{goal.id}:{today.isoformat()}:"
        f"{insights.get('radar_score')}:{insights.get('fatigue', {}).get('score')}"
    )
    cached = cache.get_json(key)
    if cached:
        return cached

    radar_text = "；".join(
        f"{item['label']} {round(item['value'] * 100)}%" for item in insights.get("radar", [])
    )
    fatigue = insights.get("fatigue", {})
    badges = [item["name"] for item in insights.get("achievements", []) if item.get("unlocked")]
    system = (
        "你是学情诊断教练。请基于给定统计写一段 120 字以内的诊断，"
        "指出最强项、最弱项与最值得优先改善的一件事，并给出 2 条可执行建议。"
        "必须保留关键数字，不得编造数据，只输出中文正文。"
    )
    prompt = (
        f"考试：{goal.exam_name}，剩余 {max((goal.exam_date - today).days, 0)} 天；"
        f"活跃天数 {insights.get('active_days')}；累计 {round(insights.get('total_minutes', 0) / 60)} 小时；"
        f"能力雷达：{radar_text}；综合指数 {insights.get('radar_score')}；"
        f"疲劳指数 {fatigue.get('score')}（{fatigue.get('level')}）：{'；'.join(fatigue.get('factors', []))}；"
        f"已解锁徽章：{'、'.join(badges) or '暂无'}。"
    )
    text = await llm.chat(system, prompt, temperature=0.4, max_tokens=360)
    if text:
        result = {"text": text.strip()[:600], "engine": "llm"}
        cache.set_json(key, result, ttl=1800)
        return result
    return fallback


async def ai_forecast_strategy(forecast: Dict, goal: Goal) -> Dict:
    fallback = {"text": forecast.get("recommendation", ""), "engine": "rule"}
    if not llm.available:
        return fallback

    key = (
        f"ai:forecast:{goal.id}:{forecast.get('current_mastery')}:"
        f"{forecast.get('projected_mastery')}:{forecast.get('required_daily_minutes')}:"
        f"{forecast.get('days_left')}"
    )
    cached = cache.get_json(key)
    if cached:
        return cached

    scenarios = "；".join(
        f"{item['label']}每天{item['daily_minutes']}分钟→{round(item['projected_mastery'] * 100)}%"
        for item in forecast.get("scenarios", [])
    )
    system = (
        "你是考前冲刺策略教练。请基于预测结果写一段 100 字以内的冲刺建议，"
        "要说明优先投入方向、是否需要提高每日时长、以及一个风险提醒。"
        "必须保留关键数字，不得改变预测值，只输出中文正文。"
    )
    prompt = (
        f"考试：{goal.exam_name}；剩余 {forecast.get('days_left')} 天；"
        f"当前掌握度 {round(forecast.get('current_mastery', 0) * 100)}%；"
        f"按当前节奏预计 {round(forecast.get('projected_mastery', 0) * 100)}%；"
        f"目标 {round(forecast.get('target_mastery', 0) * 100)}%；"
        f"达标所需每日时长 {forecast.get('required_daily_minutes')} 分钟；情景：{scenarios}。"
    )
    text = await llm.chat(system, prompt, temperature=0.4, max_tokens=320)
    if text:
        result = {"text": text.strip()[:500], "engine": "llm"}
        cache.set_json(key, result, ttl=1800)
        return result
    return fallback


async def _external_notes(term: str) -> Dict:
    """查询外部知识库，取回真实百科/学术摘要；失败时静默降级。"""
    try:
        data = await knowledge_base.lookup(term)
    except Exception:
        return {"available": False, "sources": []}
    sources = [
        {
            "name": item["name"],
            "summary": item["summary"],
            "link": item["link"],
            "status": item["status"],
        }
        for item in data.get("sources", [])
        if item.get("status") == "ok" and item.get("summary")
    ]
    return {"available": bool(sources), "sources": sources}


async def ai_flashcard_explanation(
    point: KnowledgePoint, parent_name: Optional[str], mastery: float
) -> Dict:
    key = f"ai:card:{point.id}"
    cached = cache.get_json(key) if llm.available else None
    if cached and cached.get("external"):
        return cached

    external = await _external_notes(point.name)
    fallback = {
        "explanation": f"「{point.name}」属于「{parent_name or '核心模块'}」，当前掌握度 {round(mastery * 100)}%。",
        "memory_tip": "先用自己的话复述定义，再举一个例子；24 小时内再回忆一次。",
        "misconception": "概念类知识点最常见的错误是把相近术语混用，注意区分定义边界。",
        "engine": "rule",
        "external": external,
    }
    if not llm.available:
        cache.set_json(key, fallback, ttl=3600)
        return fallback

    system = (
        "你是学习卡片助手。请为给定知识点生成助记内容，输出 JSON："
        '{"explanation":"一句话解释","memory_tip":"一条记忆技巧","misconception":"一个常见误区"}。'
        "每项不超过 60 字，中文，具体可执行，只输出 JSON。"
    )
    prompt = (
        f"知识点：{point.name}；所属模块：{parent_name or '核心模块'}；"
        f"权重：{point.weight}；当前掌握度：{round(mastery * 100)}%。"
    )
    data = await llm.chat_json(system, prompt)
    if isinstance(data, dict):
        explanation = str(data.get("explanation", "")).strip()
        memory_tip = str(data.get("memory_tip", "")).strip()
        misconception = str(data.get("misconception", "")).strip()
        if explanation:
            result = {
                "explanation": explanation[:200],
                "memory_tip": memory_tip[:200] or fallback["memory_tip"],
                "misconception": misconception[:200] or fallback["misconception"],
                "engine": "llm",
                "external": external,
            }
            cache.set_json(key, result, ttl=86400)
            return result
    return fallback