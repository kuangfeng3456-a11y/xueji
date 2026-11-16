"""多智能体学习评审团：计划官、诊断官、风险官、教练协作审查学习决策。"""

import json
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import Goal, KnowledgeGap, LearningExperiment, Task, User
from .evidence import record_evidence
from .readiness import build_risks, compute_readiness

ROLES = ["计划官", "诊断官", "风险官", "教练"]


def _fallback(
    readiness: Dict, risks: List[Dict], gaps: int, tasks: int, minutes: int, experiments: int
) -> Dict:
    opinions = [
        {
            "role": "计划官",
            "view": f"今日有 {tasks} 个任务、约 {minutes} 分钟，负荷比 {round(readiness['load_ratio'] * 100)}%。",
            "concern": "任务量与可用时间不匹配" if readiness["load_ratio"] > 1 else "节奏基本可控",
            "suggestion": "优先保留 1 个高优先级任务" if readiness["load_ratio"] > 1 else "按当前顺序执行",
        },
        {
            "role": "诊断官",
            "view": f"准备度 {readiness['score']}%，已验证漏洞 {gaps} 个。",
            "concern": "掌握度覆盖不足" if readiness["coverage"] < 0.5 else "知识覆盖尚可",
            "suggestion": "先修复高权重薄弱点并做验证题" if gaps else "继续用探针寻找隐藏盲区",
        },
        {
            "role": "风险官",
            "view": f"识别到 {len(risks)} 类风险。",
            "concern": risks[0]["reason"] if risks else "暂无高风险",
            "suggestion": risks[0]["suggestion"] if risks else "保持监测",
        },
        {
            "role": "教练",
            "view": f"已进行 {experiments} 次策略实验。",
            "concern": "策略偏好数据不足" if experiments < 1 else "已有个人策略基线",
            "suggestion": "做一次 3 天小实验" if experiments < 1 else "按收益最高的策略执行",
        },
    ]
    if not risks:
        votes = ["支持", "支持", "支持", "支持"]
    else:
        support = len([risk for risk in risks if risk["level"] != "high"]) + 1
        votes = ["支持" if index < min(4, support) else "保留" for index in range(4)]
    verdict = (
        "评审团建议：先处理最高风险，再执行今日关键任务；暂不扩大学习范围。"
        if risks
        else "评审团建议：当前状态稳定，可适度增加迁移与挑战训练。"
    )
    return {"opinions": opinions, "verdict": verdict, "votes": votes}


async def run_review(
    db: Session, user: User, goal: Goal, topic: str, today: Optional[date] = None
) -> Dict:
    today = today or date.today()
    readiness = compute_readiness(db, user, goal, today)
    risks = build_risks(db, user, goal, today)
    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id,
            KnowledgeGap.goal_id == goal.id,
            KnowledgeGap.status == "verified",
        )
    ).all()
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        )
    ).all()
    experiments = db.scalars(
        select(LearningExperiment).where(
            LearningExperiment.user_id == user.id,
            LearningExperiment.goal_id == goal.id,
        )
    ).all()

    payload = {
        "topic": topic,
        "preparedness": readiness["score"],
        "coverage": readiness["coverage"],
        "load_ratio": readiness["load_ratio"],
        "risks": [{"title": risk["title"], "level": risk["level"], "reason": risk["reason"]} for risk in risks],
        "gaps": len(gaps),
        "today_tasks": len(tasks),
        "today_minutes": sum(task.duration_min for task in tasks),
        "experiments": len(experiments),
    }

    result = None
    engine = "rule"
    if llm.available:
        system = (
            "你是学迹学习评审团主持人。请让四个角色分别发言：计划官、诊断官、风险官、教练。"
            "每个角色给出 view（观察）、concern（担忧）、suggestion（建议），"
            "最后给出 verdict（总裁决）和 votes（四个角色的支持/保留）。输出 JSON："
            '{"opinions":[{"role":"计划官","view":"","concern":"","suggestion":""}],'
            '"verdict":"","votes":["支持","支持","保留","支持"]}。只输出 JSON。'
        )
        prompt = f"议题：{topic}\n事实数据：{json.dumps(payload, ensure_ascii=False)}"
        candidate = await llm.chat_json(system, prompt)
        if isinstance(candidate, dict) and isinstance(candidate.get("opinions"), list):
            opinions = []
            for item in candidate["opinions"][:4]:
                if not isinstance(item, dict):
                    continue
                opinions.append(
                    {
                        "role": str(item.get("role", ""))[:12],
                        "view": str(item.get("view", ""))[:200],
                        "concern": str(item.get("concern", ""))[:200],
                        "suggestion": str(item.get("suggestion", ""))[:200],
                    }
                )
            if len(opinions) >= 3:
                votes = candidate.get("votes")
                result = {
                    "opinions": opinions,
                    "verdict": str(candidate.get("verdict", ""))[:400],
                    "votes": [str(vote)[:8] for vote in votes] if isinstance(votes, list) else [],
                }
                engine = "llm"
    if result is None:
        result = _fallback(readiness, risks, len(gaps), len(tasks), sum(t.duration_min for t in tasks), len(experiments))

    from ..models import PanelReview

    review = PanelReview(
        user_id=user.id,
        goal_id=goal.id,
        topic=topic[:120],
        opinions=json.dumps(result["opinions"], ensure_ascii=False),
        verdict=result["verdict"],
        votes=json.dumps(result["votes"], ensure_ascii=False),
        engine=engine,
    )
    db.add(review)
    record_evidence(
        db,
        user.id,
        goal.id,
        "panel_review",
        topic[:60],
        payload,
        result["verdict"],
        engine=engine,
    )
    db.commit()
    db.refresh(review)
    return {
        "id": review.id,
        "topic": review.topic,
        "opinions": result["opinions"],
        "verdict": review.verdict,
        "votes": result["votes"],
        "engine": review.engine,
        "created_at": review.created_at,
    }

DEBATE_AGENTS = [
    ("planner", "计划官"),
    ("diagnoser", "诊断官"),
    ("tutor", "学科导师"),
    ("predictor", "预测官"),
    ("evidence_reviewer", "证据审查官"),
    ("challenger", "挑刺官"),
]


def _stance(condition_support: bool) -> str:
    return "支持" if condition_support else "保留"


def _rule_debate(payload: Dict) -> List[Dict]:
    readiness = payload["readiness"]
    risks = payload["risks"]
    high_risks = [risk for risk in risks if risk.get("level") == "high"]
    coverage = readiness.get("coverage", 0.0)
    load_ratio = readiness.get("load_ratio", 0.0)
    gaps = payload["verified_gaps"]
    experiments = payload["experiments"]
    insufficient = payload["risk_insufficient"]
    high_risk_points = payload["high_risk_points"]

    opinions = []

    planner_support = load_ratio <= 1.0
    opinions.append(
        {
            "agent": "planner",
            "role": "计划官",
            "stance": _stance(planner_support),
            "view": f"今日任务 {payload['today_tasks']} 个、约 {payload['today_minutes']} 分钟，负荷比 {round(load_ratio * 100)}%。",
            "evidence": [
                f"今日任务数={payload['today_tasks']}",
                f"负荷比={round(load_ratio * 100)}%",
            ],
            "concern": "任务量与可用时间不匹配" if not planner_support else "节奏基本可控",
            "suggestion": "压缩低优先级任务，保留 1 个高优先级任务" if not planner_support else "按当前顺序执行",
        }
    )

    diagnoser_support = coverage >= 0.5
    opinions.append(
        {
            "agent": "diagnoser",
            "role": "诊断官",
            "stance": _stance(diagnoser_support),
            "view": f"准备度 {readiness.get('score', 0)}%，知识覆盖 {round(coverage * 100)}%，已验证漏洞 {gaps} 个。",
            "evidence": [
                f"准备度={readiness.get('score', 0)}%",
                f"覆盖率={round(coverage * 100)}%",
                f"已验证漏洞={gaps}",
            ],
            "concern": "知识覆盖不足" if not diagnoser_support else "知识覆盖尚可",
            "suggestion": "先修复高权重薄弱点" if not diagnoser_support else "继续用探针寻找隐藏盲区",
        }
    )

    tutor_support = bool(high_risk_points) or gaps > 0
    opinions.append(
        {
            "agent": "tutor",
            "role": "学科导师",
            "stance": _stance(tutor_support),
            "view": f"发现 {len(high_risk_points)} 个高风险知识点，建议先讲清概念再练迁移题。",
            "evidence": [f"高风险知识点={len(high_risk_points)}", f"已验证漏洞={gaps}"],
            "concern": "概念未稳时直接刷题收益低" if high_risk_points else "可进入迁移训练",
            "suggestion": "先做苏格拉底式讲解，再做变式题" if high_risk_points else "用迁移题验证理解深度",
        }
    )

    risk_support = not high_risks
    opinions.append(
        {
            "agent": "predictor",
            "role": "预测官",
            "stance": _stance(risk_support),
            "view": f"预测到 {len(risks)} 类备考风险，其中高风险 {len(high_risks)} 类，风险样本 {payload['risk_sample']} 条。",
            "evidence": [risk.get("title", "") for risk in risks[:3]] or ["暂无风险数据"],
            "concern": high_risks[0]["reason"] if high_risks else "暂无高风险",
            "suggestion": high_risks[0]["suggestion"] if high_risks else "保持监测",
        }
    )

    evidence_support = insufficient == 0 and experiments > 0
    opinions.append(
        {
            "agent": "evidence_reviewer",
            "role": "证据审查官",
            "stance": _stance(evidence_support),
            "view": f"风险证据不足项 {insufficient} 个，已完成策略实验 {experiments} 次。",
            "evidence": [
                f"证据不足={insufficient}",
                f"策略实验={experiments}",
                f"风险样本={payload['risk_sample']}",
            ],
            "concern": "数据不足时不宜下强结论" if not evidence_support else "证据链基本完整",
            "suggestion": "先补验证题与实验，再扩大结论" if not evidence_support else "可进入裁决",
        }
    )
    premortem_support = not (bool(high_risks) and insufficient > 2)
    opinions.append(
        {
            "agent": "challenger",
            "role": "挑刺官",
            "stance": _stance(premortem_support),
            "view": "事前验尸：假设三周后失败，最可能的原因是执行中断、先修补不齐与证据不足。",
            "evidence": [
                f"高风险={len(high_risks)}",
                f"证据不足={insufficient}",
                f"今日任务={payload['today_tasks']}",
            ],
            "concern": "若中断超过 3 天，当前计划会整体失效" if not premortem_support else "暂未发现致命假设",
            "suggestion": "先设置最小任务与恢复站，确保中断后能回来" if not premortem_support else "保留每周一次复盘挑战",
        }
    )
    return opinions


def _arbitrate(opinions: List[Dict]) -> Dict:
    total = len(opinions)
    support = len([item for item in opinions if item["stance"] == "支持"])
    dissent = [
        f"{item['role']}：{item['concern']}"
        for item in opinions
        if item["stance"] != "支持"
    ]
    score = round(support / total * 100, 1) if total else 0.0
    if score >= 60:
        decision = "采纳当前计划，并优先处理分歧中提到的风险"
    else:
        decision = "暂缓扩大学习范围，先补齐证据并修复高风险点"
    rationale = (
        f"{total} 个角色中 {support} 个支持、{total - support} 个保留；"
        f"裁决依据为可复算的支持票比例与证据完整性。"
    )
    return {
        "decision": decision,
        "score": score,
        "rationale": rationale,
        "dissent": dissent,
        "rule_version": "arbiter-v2",
    }


async def run_debate(
    db: Session, user: User, goal: Goal, topic: str, today: Optional[date] = None
) -> Dict:
    import time
    import uuid
    from datetime import datetime

    from ..models import AgentRun, PanelReview, RiskPrediction
    from .risk_forecast import compute_risks

    started = time.perf_counter()
    today = today or date.today()
    readiness = compute_readiness(db, user, goal, today)
    risks = build_risks(db, user, goal, today)
    gaps = db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.user_id == user.id,
            KnowledgeGap.goal_id == goal.id,
            KnowledgeGap.status == "verified",
        )
    ).all()
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.goal_id == goal.id,
            Task.day == today,
            Task.status == "pending",
        )
    ).all()
    experiments = db.scalars(
        select(LearningExperiment).where(
            LearningExperiment.user_id == user.id,
            LearningExperiment.goal_id == goal.id,
            LearningExperiment.status == "finished",
        )
    ).all()
    risk_rows = compute_risks(db, user, goal, today)
    high_risk_points = [item for item in risk_rows if item["level"] == "high"]
    risk_sample = sum(item["sample_size"] for item in risk_rows)

    payload = {
        "topic": topic,
        "readiness": {
            "score": readiness["score"],
            "coverage": readiness["coverage"],
            "load_ratio": readiness["load_ratio"],
        },
        "risks": [
            {"title": risk["title"], "level": risk["level"], "reason": risk["reason"],
             "suggestion": risk["suggestion"]}
            for risk in risks
        ],
        "verified_gaps": len(gaps),
        "today_tasks": len(tasks),
        "today_minutes": sum(task.duration_min for task in tasks),
        "experiments": len(experiments),
        "risk_insufficient": len([item for item in risk_rows if item["evidence"].get("insufficient")]),
        "high_risk_points": [item["kp_name"] for item in high_risk_points],
        "risk_sample": risk_sample,
    }

    opinions = _rule_debate(payload)
    engine = "rule"
    model_version = ""
    prompt_version = "panel-v2"

    if llm.available:
        system = (
            "你是学迹多智能体辩论主持人。请基于事实数据，为五个角色分别给出更自然的表达。"
            "角色：planner(计划官)、diagnoser(诊断官)、tutor(学科导师)、predictor(预测官)、"
            "evidence_reviewer(证据审查官)、challenger(挑刺官)。"
            "evidence_reviewer(证据审查官)。输出 JSON："
            '{"opinions":[{"agent":"planner","view":"","concern":"","suggestion":""}]}。'
            "只改写 view/concern/suggestion，不要改变立场。只输出 JSON。"
        )
        prompt = "议题：" + topic + "\n事实：" + json.dumps(payload, ensure_ascii=False)
        candidate = await llm.chat_json(system, prompt)
        if isinstance(candidate, dict) and isinstance(candidate.get("opinions"), list):
            by_agent = {
                str(item.get("agent", "")).strip(): item
                for item in candidate["opinions"]
                if isinstance(item, dict)
            }
            polished = 0
            for opinion in opinions:
                extra = by_agent.get(opinion["agent"])
                if not extra:
                    continue
                for key in ("view", "concern", "suggestion"):
                    text = str(extra.get(key, "")).strip()
                    if text:
                        opinion[key] = text[:220]
                        polished += 1
            if polished:
                engine = "llm"
                model_version = llm.model
        arbiter = _arbitrate(opinions)
    else:
        arbiter = _arbitrate(opinions)

    latency_ms = int((time.perf_counter() - started) * 1000)
    run_id = uuid.uuid4().hex[:24]
    created_at = datetime.utcnow()

    for order, opinion in enumerate(opinions):
        db.add(
            AgentRun(
                run_id=run_id,
                user_id=user.id,
                goal_id=goal.id,
                agent_name=opinion["role"],
                role_order=order,
                input_ref=f"topic:{topic[:60]}",
                output=json.dumps(opinion, ensure_ascii=False),
                evidence=json.dumps(opinion["evidence"], ensure_ascii=False),
                status="ok" if engine == "llm" else "fallback",
                engine=engine,
                model_version=model_version,
                prompt_version=prompt_version,
                latency_ms=latency_ms,
            )
        )

    review = PanelReview(
        user_id=user.id,
        goal_id=goal.id,
        topic=topic[:120],
        opinions=json.dumps(opinions, ensure_ascii=False),
        verdict=f"{arbiter['decision']}；{arbiter['rationale']}",
        votes=json.dumps([item["stance"] for item in opinions], ensure_ascii=False),
        engine=engine,
    )
    db.add(review)
    record_evidence(
        db,
        user.id,
        goal.id,
        "agent_debate",
        topic[:60],
        payload,
        f"{arbiter['decision']}（支持率 {arbiter['score']}%）",
        engine=engine,
    )
    db.commit()
    return {
        "run_id": run_id,
        "topic": topic,
        "opinions": opinions,
        "arbiter": arbiter,
        "engine": engine,
        "created_at": created_at,
    }


def list_agent_runs(
    db: Session, user: User, goal: Goal, run_id: Optional[str] = None, limit: int = 30
) -> List[Dict]:
    from ..models import AgentRun

    query = select(AgentRun).where(AgentRun.user_id == user.id, AgentRun.goal_id == goal.id)
    if run_id:
        query = query.where(AgentRun.run_id == run_id)
    rows = db.scalars(query.order_by(AgentRun.created_at.desc()).limit(limit)).all()
    result = []
    for row in rows:
        try:
            output = json.loads(row.output)
        except Exception:
            output = {}
        try:
            evidence = json.loads(row.evidence)
        except Exception:
            evidence = []
        result.append(
            {
                "run_id": row.run_id,
                "agent_name": row.agent_name,
                "role_order": row.role_order,
                "status": row.status,
                "engine": row.engine,
                "model_version": row.model_version,
                "prompt_version": row.prompt_version,
                "latency_ms": row.latency_ms,
                "output": output,
                "evidence": evidence,
                "created_at": row.created_at,
            }
        )
    return result