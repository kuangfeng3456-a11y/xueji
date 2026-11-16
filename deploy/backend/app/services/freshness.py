"""学习内容时效雷达：发现资料与知识版本过时问题。"""

import json
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import FreshnessReport, Goal, Material, User
from .evidence import record_evidence


def _rule_scan(material: Material, current_year: int) -> Dict:
    text = material.content or ""
    years = [int(year) for year in re.findall(r"20(?:1[5-9]|2[0-9])", text)]
    latest = max(years) if years else None
    issues = []
    if latest is None:
        issues.append("资料中没有标注年份或大纲版本，无法判断是否覆盖最新考纲")
    elif latest < current_year - 1:
        issues.append(f"资料最新年份为 {latest}，可能缺少 {current_year} 年新题型或大纲变化")
    if "大纲" not in text and "考纲" not in text:
        issues.append("未发现考纲对照，建议补充最新考试说明")
    if len(text) < 200:
        issues.append("资料内容较少，难以判断覆盖范围")
    if latest is None:
        score = 55
    else:
        score = max(20, 90 - max(0, current_year - latest) * 10)
    suggestion = "核对最新考试大纲，补充近两年真题与新增题型。"
    return {
        "score": score,
        "issues": issues[:4],
        "suggestion": suggestion,
        "engine": "rule",
    }


async def scan_freshness(db: Session, user: User, goal: Goal) -> Dict:
    materials = db.scalars(
        select(Material).where(Material.user_id == user.id, Material.goal_id == goal.id)
    ).all()
    current_year = date.today().year
    items = []
    for material in materials[:5]:
        data = None
        engine = "rule"
        if llm.available:
            system = (
                f"你是学习资料时效审查员。当前年份 {current_year}，考试为 {goal.exam_name}。"
                "请评估资料是否过时，输出 JSON："
                '{"score":80,"issues":["具体问题"],"suggestion":"一句补充建议"}。'
                "score 取 0-100，issues 最多 3 条，只输出 JSON。"
            )
            prompt = (
                f"资料名：{material.filename}\n内容摘录：{(material.content or '')[:1500]}"
            )
            candidate = await llm.chat_json(system, prompt)
            if isinstance(candidate, dict) and isinstance(candidate.get("score"), int):
                issues = candidate.get("issues")
                data = {
                    "score": max(0, min(100, candidate["score"])),
                    "issues": [str(item)[:120] for item in issues[:3]] if isinstance(issues, list) else [],
                    "suggestion": str(candidate.get("suggestion", ""))[:200]
                    or "核对最新考试大纲与真题。",
                    "engine": "llm",
                }
                engine = "llm"
        if data is None:
            data = _rule_scan(material, current_year)

        report = db.scalar(
            select(FreshnessReport).where(FreshnessReport.material_id == material.id)
        )
        if report is None:
            report = FreshnessReport(
                user_id=user.id,
                goal_id=goal.id,
                material_id=material.id,
                score=data["score"],
                issues=json.dumps(data["issues"], ensure_ascii=False),
                suggestion=data["suggestion"],
                engine=engine,
                checked_at=datetime.utcnow(),
            )
            db.add(report)
        else:
            report.score = data["score"]
            report.issues = json.dumps(data["issues"], ensure_ascii=False)
            report.suggestion = data["suggestion"]
            report.engine = engine
            report.checked_at = datetime.utcnow()

        items.append(
            {
                "material_id": material.id,
                "filename": material.filename,
                "score": data["score"],
                "level": "fresh" if data["score"] >= 80 else "warning" if data["score"] >= 60 else "stale",
                "issues": data["issues"],
                "suggestion": data["suggestion"],
                "engine": engine,
            }
        )
        record_evidence(
            db,
            user.id,
            goal.id,
            "freshness_scan",
            material.filename,
            {"score": data["score"], "issues": data["issues"]},
            data["suggestion"],
            engine=engine,
        )
    db.commit()
    overall = round(sum(item["score"] for item in items) / len(items)) if items else 0
    return {
        "items": items,
        "overall": overall,
        "scanned_at": datetime.utcnow(),
    }