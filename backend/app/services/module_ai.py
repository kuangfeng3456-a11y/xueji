"""为每个业务模块提供对应角色的大模型能力。

每个模块有独立角色与提示词，输出统一结构 {headline, insights, actions}。
上下文来自真实数据库与真实计算结果；模型不可用时用规则文案兜底。
"""

import json
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..cache import cache
from ..llm import llm
from ..prompts.library import build_messages, check_envelope, parse_json_strict
from ..models import (
    Buddy,
    ClassMember,
    Goal,
    KnowledgeGap,
    KnowledgePoint,
    LearningExperiment,
    Mastery,
    Mistake,
    Task,
    User,
)

MODULES: Dict[str, Dict] = {
    "cockpit": {
        "name": "驾驶舱教练",
        "role": "学习驾驶舱教练",
        "focus": "解读准备度、关键任务与风险，给出今天最该做的三件事",
    },
    "knowledge_map": {
        "name": "知识漏洞诊断师",
        "role": "知识漏洞诊断师",
        "focus": "解读薄弱知识点与先修依赖，指出修复顺序",
    },
    "sprint": {
        "name": "冲刺规划师",
        "role": "考前冲刺规划师",
        "focus": "解读未来模拟结果，说明时间投入与可达目标",
    },
    "risk_center": {
        "name": "风险分析师",
        "role": "学习风险分析师",
        "focus": "解读当前风险来源，给出救援优先级",
    },
    "experiments": {
        "name": "学习科学家",
        "role": "学习策略实验科学家",
        "focus": "解读策略实验收益，建议下一个实验",
    },
    "evidence": {
        "name": "证据链审计员",
        "role": "学习证据审计员",
        "focus": "解释系统给出的判断依据，指出可以复核的数据",
    },
    "class": {
        "name": "教学分析师",
        "role": "面向教师的教学分析师",
        "focus": "解读班级共同薄弱点，给出统一复习建议",
    },
    "buddies": {
        "name": "学习社群教练",
        "role": "学习社群教练",
        "focus": "给出与学习搭子互相督促的具体建议",
    },
    "market": {
        "name": "学科 Skill 顾问",
        "role": "学科学习方法顾问",
        "focus": "根据当前目标推荐可用的学科 Skill 包与学习路径",
    },
    "fun_zone": {
        "name": "学习节奏顾问",
        "role": "学习节奏与恢复顾问",
        "focus": "把休息娱乐与学习恢复结合，给出一条可执行的放松建议",
    },
    "focus": {
        "name": "专注教练",
        "role": "专注力教练",
        "focus": "给出本轮强制学习的专注策略与中断应对",
    },
    "goal": {
        "name": "目标规划师",
        "role": "学习目标规划师",
        "focus": "解读目标合理性，给出资料与时间安排建议",
    },
    "skills": {
        "name": "能力架构师",
        "role": "AI 能力架构师",
        "focus": "解释四个智能体与 Skills 如何协同，指出可扩展方向",
    },
    "freshness": {
        "name": "资料时效顾问",
        "role": "备考资料时效顾问",
        "focus": "解读资料时效扫描结果，给出补资料优先级",
    },
    "dashboard": {
        "name": "学习总教练",
        "role": "学习总教练",
        "focus": "解读今日任务与掌握度趋势，给出今天最该做的三件事",
    },
    "insights": {
        "name": "学习洞察师",
        "role": "学习数据洞察分析师",
        "focus": "解读热力图与雷达图，指出学习习惯与能力短板",
    },
    "mistakes": {
        "name": "错题诊断师",
        "role": "错题归因诊断师",
        "focus": "解读错题分布与错因分类，给出补救建议",
    },
    "report": {
        "name": "周报教练",
        "role": "学习周报教练",
        "focus": "解读本周完成率与掌握度变化，给出下周建议",
    },
    "plan": {
        "name": "计划排程师",
        "role": "学习计划排程师",
        "focus": "解读任务排程与优先级，给出调整建议",
    },
    "ai_lab": {
        "name": "探针出题官",
        "role": "AI 探针出题官",
        "focus": "解读探针结果与盲区发现，给出下一步探测建议",
    },
    "panel": {
        "name": "评审团教练",
        "role": "多智能体评审团教练",
        "focus": "解读评审意见与投票结果，给出决策建议",
    },
    "mind_care": {
        "name": "心理顾问",
        "role": "学习心理顾问",
        "focus": "解读压力与疲劳状态，给出心理调节建议",
    },
    "flashcards": {
        "name": "记忆教练",
        "role": "间隔重复记忆教练",
        "focus": "解读复习进度与遗忘曲线，给出记忆策略建议",
    },
    "quiz": {
        "name": "测验教练",
        "role": "随堂测教练",
        "focus": "解读测验结果与错因分布，给出补练建议",
    },
    "integrations": {
        "name": "接入顾问",
        "role": "系统集成顾问",
        "focus": "解读接入状态与数据源，给出配置建议",
    },
}

CACHE_TTL = 1800


def module_list() -> List[Dict]:
    return [
        {"key": key, "name": meta["name"], "role": meta["role"], "focus": meta["focus"]}
        for key, meta in MODULES.items()
    ]


def _base_context(db: Session, user: User, goal: Optional[Goal]) -> Dict:
    context: Dict = {
        "用户昵称": user.nickname,
        "目标": goal.exam_name if goal else "未设置目标",
        "剩余天数": None,
    }
    if goal:
        context["剩余天数"] = max((goal.exam_date - date.today()).days, 0)
        context["每日计划分钟"] = goal.daily_minutes

    if goal:
        points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
        point_ids = [point.id for point in points] or [0]
        context["知识点数"] = len(points)
        rows = db.scalars(
            select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id.in_(point_ids))
        ).all()
        context["平均掌握度"] = round(sum(row.value for row in rows) / len(rows), 3) if rows else 0.0
        weak = sorted(
            ((point.name, next((row.value for row in rows if row.kp_id == point.id), 0.0)) for point in points),
            key=lambda item: item[1],
        )[:3]
        context["最薄弱知识点"] = [name for name, _ in weak]

        tasks = db.scalars(
            select(Task).where(
                Task.user_id == user.id,
                Task.goal_id == goal.id,
                Task.day == date.today(),
            )
        ).all()
        context["今日任务数"] = len(tasks)
        context["今日已完成"] = len([task for task in tasks if task.status == "done"])

        since = date.today() - timedelta(days=7)
        context["近7天错题数"] = db.scalar(
            select(func.count(Mistake.id)).where(
                Mistake.user_id == user.id,
                Mistake.goal_id == goal.id,
                Mistake.created_at >= since,
            )
        ) or 0
        context["已验证漏洞数"] = db.scalar(
            select(func.count(KnowledgeGap.id)).where(
                KnowledgeGap.user_id == user.id,
                KnowledgeGap.goal_id == goal.id,
                KnowledgeGap.status == "verified",
            )
        ) or 0
        context["已完成实验数"] = db.scalar(
            select(func.count(LearningExperiment.id)).where(
                LearningExperiment.user_id == user.id,
                LearningExperiment.goal_id == goal.id,
                LearningExperiment.status == "finished",
            )
        ) or 0

    context["班级数"] = db.scalar(
        select(func.count(ClassMember.id)).where(ClassMember.user_id == user.id)
    ) or 0
    context["学习搭子数"] = db.scalar(
        select(func.count(Buddy.id)).where(Buddy.user_id == user.id)
    ) or 0
    return context


def _fallback(meta: Dict, context: Dict) -> Dict:
    weak = context.get("最薄弱知识点") or []
    return {
        "headline": f"{meta['name']}：基于当前 {context.get('今日任务数', 0)} 个任务与 {context.get('已剔除', '')}数据给出建议",
        "insights": [
            f"当前目标：{context.get('目标')}，剩余 {context.get('剩余天数') or '—'} 天",
            f"平均掌握度 {round((context.get('平均掌握度') or 0) * 100)}%，近 7 天错题 {context.get('近7天错题数', 0)} 道",
            f"薄弱知识点：{'、'.join(weak) if weak else '暂无'}",
        ],
        "actions": [
            "先完成今日最高优先级任务",
            "对最薄弱知识点安排一次针对性复习",
        ],
    }


async def generate(module_key: str, db: Session, user: User, goal: Optional[Goal]) -> Dict:
    meta = MODULES.get(module_key)
    if not meta:
        raise ValueError("未知模块")

    context = _base_context(db, user, goal)
    day_key = date.today().isoformat()
    cache_key = f"module-ai:{module_key}:{user.id}:{goal.id if goal else 0}:{day_key}"
    cached = cache.get_json(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    fallback = _fallback(meta, context)
    result = {
        "module": module_key,
        "name": meta["name"],
        "role": meta["role"],
        "focus": meta["focus"],
        "headline": fallback["headline"],
        "insights": fallback["insights"],
        "actions": fallback["actions"],
        "engine": "rule",
        "context": context,
        "generated_at": date.today().isoformat(),
        "cached": False,
    }

    if llm.available:
        # 文档 7.1：ModuleAI 统一走决策解释官 P12，输出仍是统一信封
        messages, prompt_meta = build_messages(
            "P12",
            module_name=module_key,
            module_data_json=context,
            learner_state_json={
                "goal": context.get("目标"),
                "days_left": context.get("剩余天数"),
                "avg_mastery": context.get("平均掌握度"),
            },
        )
        raw = await llm.chat(
            messages[0]["content"],
            messages[1]["content"] if len(messages) > 1 else "",
            temperature=prompt_meta["temperature"] or 0.4,
            max_tokens=prompt_meta["max_tokens"] or 1000,
            prompt_id=prompt_meta["prompt_id"],
            prompt_version=prompt_meta["version"],
            prompt_hash=prompt_meta["hash"],
            tier=prompt_meta["tier"] or "general",
            user_id=user.id,
        )
        payload = None
        if raw:
            try:
                envelope = parse_json_strict(raw)
            except ValueError:
                envelope = None
            if isinstance(envelope, dict) and not check_envelope(envelope):
                payload = envelope.get("data") or {}
                result["prompt"] = {
                    "id": prompt_meta["prompt_id"],
                    "version": prompt_meta["version"],
                    "hash": prompt_meta["hash"],
                }
                if payload.get("caveats"):
                    result["caveats"] = [str(item) for item in payload["caveats"]][:3]
                if envelope.get("warnings"):
                    result["warnings"] = [str(item) for item in envelope["warnings"]][:5]
        if isinstance(payload, dict):
            insights: List[str] = []
            for item in (payload.get("insights") or [])[:3]:
                if isinstance(item, dict):
                    finding = str(item.get("finding", "")).strip()
                    so_what = str(item.get("so_what", "")).strip()
                    text = f"{finding}：{so_what}" if finding and so_what else (finding or so_what)
                else:
                    text = str(item).strip()
                if text:
                    insights.append(text[:120])
            actions = [
                str(item).strip()[:60]
                for item in (payload.get("next_actions") or [])
                if str(item).strip()
            ]
            if insights:
                result.update(
                    {
                        "headline": insights[0][:60],
                        "insights": insights,
                        "actions": actions[:3] or result["actions"],
                        "engine": "llm",
                    }
                )
            else:
                result["ai_note"] = "数据不足，保留规则分析（P12 未生成洞察）"

    cache.set_json(cache_key, result, ttl=CACHE_TTL)
    return result