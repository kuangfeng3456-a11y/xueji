"""AI 苏格拉底导师、复述检查与学习资源工厂。"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import Goal, KnowledgePoint, Mastery, User
from .learning_events import record_event
from .validator import scan_text

LEVEL_LABELS = {
    "direction": "方向提示",
    "concept": "概念提示",
    "step": "步骤提示",
    "full": "完整讲解",
}
MODE_LABELS = {
    "hint": "提示模式",
    "explain": "讲解模式",
    "exam": "考试模式",
}
RESOURCE_LABELS = {
    "flashcard": "闪卡",
    "variant": "变式题",
    "outline": "微课提纲",
}


def _point(db: Session, kp_id: int) -> KnowledgePoint:
    point = db.get(KnowledgePoint, kp_id)
    if point is None:
        raise ValueError("知识点不存在")
    return point


def _rule_reply(point: KnowledgePoint, message: str, mode: str, level: str) -> Dict:
    name = point.name
    if mode == "exam":
        reply = (
            f"考试模式下我不提供讲解。请先独立完成与「{name}」相关的一道题，"
            "再提交你的思路，我会指出关键卡点。"
        )
        next_question = f"请说出「{name}」的核心定义或判断条件。"
    elif level == "direction":
        reply = (
            f"先不要急着算。围绕「{name}」，请你先回答：题目要求你求什么？"
            "它和哪些已知条件直接相关？"
        )
        next_question = f"「{name}」在这道题里对应的是哪个条件？"
    elif level == "concept":
        reply = (
            f"「{name}」的关键在于先明确它的定义与适用条件，再看题目是否满足。"
            "说出定义后，我们再决定用哪种方法。"
        )
        next_question = f"你能用自己的话复述「{name}」的适用条件吗？"
    elif level == "step":
        reply = (
            f"按三步走：①识别题目属于「{name}」的哪类问题；②列出已知与所求；"
            "③选择对应方法并检查边界条件。你在哪一步卡住？"
        )
        next_question = "你现在卡在第几步？把已知条件写出来我看看。"
    else:
        reply = (
            f"完整讲解：「{name}」先看定义与条件，再匹配方法，最后代回检查。"
            "讲解后请用你自己的话复述一遍，并完成一道变式题确认掌握。"
        )
        next_question = "请用一句话复述「{name}」的解题流程。"
    return {
        "reply": reply,
        "level": level,
        "level_label": LEVEL_LABELS.get(level, level),
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "next_question": next_question,
        "engine": "rule",
    }


async def socratic_reply(
    db: Session,
    user: User,
    goal: Goal,
    kp_id: int,
    message: str,
    mode: str = "hint",
    level: str = "direction",
) -> Dict:
    point = _point(db, kp_id)
    if mode not in MODE_LABELS:
        mode = "hint"
    if level not in LEVEL_LABELS:
        level = "direction"

    result = None
    engine = "rule"
    model_version = ""
    if llm.available and mode != "exam":
        system = (
            "你是苏格拉底式学科导师。原则：优先用递进问题启发，不直接给最终答案；"
            "提示分四级：direction 方向提示、concept 概念提示、step 步骤提示、full 完整讲解。"
            "输出 JSON："
            '{"reply":"","level":"","next_question":""}。只输出 JSON。'
        )
        prompt = (
            f"知识点：{point.name}\n当前模式：{MODE_LABELS.get(mode)}\n"
            f"当前提示级别：{LEVEL_LABELS.get(level)}\n学生说：{message or '我想理解这个知识点'}"
        )
        candidate = await llm.chat_json(system, prompt)
        if isinstance(candidate, dict) and candidate.get("reply"):
            result = {
                "reply": str(candidate["reply"])[:600],
                "level": level,
                "level_label": LEVEL_LABELS.get(level),
                "mode": mode,
                "mode_label": MODE_LABELS.get(mode),
                "next_question": str(candidate.get("next_question", ""))[:200],
                "engine": "llm",
            }
            engine = "llm"
            model_version = llm.model
    if result is None:
        result = _rule_reply(point, message, mode, level)

    issues = scan_text(result.get("reply", ""))
    result["validation"] = "passed" if not issues else "flagged"
    if issues:
        result = _rule_reply(point, message, mode, level)
        result["validation"] = "fallback"
        result["engine"] = "rule"
        result["issues"] = [item["message"] for item in issues]
        engine = "rule"
        model_version = ""

    record_event(
        db,
        user.id,
        goal.id,
        "hint",
        point.id,
        {"mode": mode, "level": level, "engine": engine},
    )
    db.commit()
    result["model_version"] = model_version
    stage_map = {"direction": "点拨", "concept": "半步", "step": "半步", "full": "示范"}
    result["hint_stage"] = stage_map.get(level, "点拨")
    result["self_check"] = result.get("next_question", "")
    return result


def recall_check(db: Session, user: User, goal: Goal, kp_id: int, recall: str) -> Dict:
    point = _point(db, kp_id)
    text = (recall or "").strip()
    keywords = [point.name] + [part for part in re.split(r"[\s，。、,.;；]+", point.name) if len(part) >= 2]
    keywords = list(dict.fromkeys([item for item in keywords if item]))
    matched = [item for item in keywords if item in text]
    missing = [item for item in keywords if item not in text]
    coverage = round(len(matched) / len(keywords) * 100) if keywords else 0
    passed = coverage >= 60 and len(text) >= 12
    if passed:
        feedback = "复述覆盖了核心概念，可以进入一道变式题确认迁移。"
    elif len(text) < 12:
        feedback = "复述过短，请用 2-3 句话说明定义、条件与用法。"
    else:
        feedback = f"复述缺少关键信息：{'、'.join(missing[:3])}。请补充后再提交。"
    record_event(
        db,
        user.id,
        goal.id,
        "recall",
        point.id,
        {"coverage": coverage, "passed": passed},
    )
    db.commit()
    return {
        "kp_id": point.id,
        "kp_name": point.name,
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "passed": passed,
        "feedback": feedback,
        "version": "recall-rule-v1",
    }


def _rule_resources(point: KnowledgePoint, resource_type: str, count: int) -> List[Dict]:
    items = []
    for index in range(count):
        if resource_type == "flashcard":
            items.append(
                {
                    "front": f"{point.name}（第 {index + 1} 张）",
                    "back": f"先明确「{point.name}」的定义与适用条件，再匹配方法并检查边界。",
                    "tags": [point.name],
                }
            )
        elif resource_type == "variant":
            items.append(
                {
                    "question": f"关于「{point.name}」，请说明它的定义，并举一个满足与不满足条件的例子。",
                    "answer_points": ["定义准确", "条件完整", "例子正确"],
                }
            )
        else:
            items.append(
                {
                    "title": f"{point.name} 微课提纲",
                    "sections": ["概念定义", "适用条件", "典型例题", "常见误区", "变式练习"],
                }
            )
    return items


async def generate_resources(
    db: Session,
    user: User,
    goal: Goal,
    kp_id: int,
    resource_type: str = "flashcard",
    count: int = 3,
) -> Dict:
    point = _point(db, kp_id)
    if resource_type not in RESOURCE_LABELS:
        resource_type = "flashcard"
    count = max(1, min(count, 5))

    items = None
    engine = "rule"
    model_version = ""
    if llm.available:
        system = (
            "你是学习资源工厂。根据知识点生成结构化资源，只输出 JSON。"
            '闪卡格式 {"items":[{"front":"","back":"","tags":[]}]}；'
            '变式题格式 {"items":[{"question":"","answer_points":[]}]}；'
            '微课提纲格式 {"items":[{"title":"","sections":[]}]}。'
        )
        prompt = (
            f"知识点：{point.name}\n资源类型：{RESOURCE_LABELS[resource_type]}\n数量：{count}"
        )
        candidate = await llm.chat_json(system, prompt)
        if isinstance(candidate, dict) and isinstance(candidate.get("items"), list) and candidate["items"]:
            items = candidate["items"][:count]
            engine = "llm"
            model_version = llm.model
    if items is None:
        items = _rule_resources(point, resource_type, count)

    record_event(
        db,
        user.id,
        goal.id,
        "resource_generate",
        point.id,
        {"resource_type": resource_type, "count": len(items), "engine": engine},
    )
    db.commit()
    return {
        "kp_id": point.id,
        "kp_name": point.name,
        "resource_type": resource_type,
        "resource_label": RESOURCE_LABELS.get(resource_type, resource_type),
        "items": items,
        "engine": engine,
        "model_version": model_version,
        "review_status": "pending_review",
        "note": "生成内容为待审核状态，未审核内容不会自动进入正式题库。",
    }