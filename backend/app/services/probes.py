"""AI 主动探针出题官：主动寻找隐藏盲区，并支持迁移压力测试与反脆弱挑战。"""

import json
import random
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import item_policy
from ..llm import llm
from ..models import Goal, KnowledgePoint, Mastery, Mistake, ProbeItem, User
from .evidence import record_evidence
from .mastery_service import apply_answer

VALID_KINDS = (
    "probe",
    "transfer",
    "challenge",
    "boundary",
    "speed",
    "reverse",
    "trap",
    "mixed",
)

KIND_BRIEF = {
    "probe": "主动寻找隐藏知识盲区，重点考察概念边界与容易混淆的细节",
    "transfer": "知识迁移压力测试，必须换一个全新情境或换一种问法，考察能否举一反三",
    "challenge": "反脆弱挑战题，故意加入陌生条件或超出当前水平的元素，允许答错，重点看尝试与恢复",
    "boundary": "概念边界辨析题，给出四个高度相似的表述，只有一处细微差别决定对错",
    "speed": "限时快答题，题干要短、一眼可读，考察条件反射式的熟练度",
    "reverse": "逆向追问题，从结论或现象反推原因与条件，考察因果链是否真正理清",
    "trap": "陷阱排除题，选项中埋入两三个常见思维陷阱，考察能否识破套路",
    "mixed": "混合挑战题，一道题内融合两个知识点的交叉运用，考察综合能力",
}

KIND_LABEL = {
    "probe": "主动探针",
    "transfer": "迁移压力测试",
    "challenge": "反脆弱挑战",
    "boundary": "概念边界辨析",
    "speed": "限时快答",
    "reverse": "逆向追问",
    "trap": "陷阱排除",
    "mixed": "混合挑战",
}

# 训练型题型：答错不惩罚掌握度
TRAINING_KINDS = ("challenge", "speed", "trap", "mixed")


def _leaves(db: Session, goal_id: int) -> List[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    return [point for point in points if point.id not in parent_ids] or points


def _mastery(db: Session, user_id: int, goal_id: int) -> Dict[int, float]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    return {row.kp_id: row.value for row in rows}


def _mistake_counts(db: Session, user_id: int, goal_id: int) -> Dict[int, int]:
    rows = db.scalars(
        select(Mistake).where(Mistake.user_id == user_id, Mistake.goal_id == goal_id)
    ).all()
    counts: Dict[int, int] = {}
    for row in rows:
        if row.kp_id:
            counts[row.kp_id] = counts.get(row.kp_id, 0) + 1
    return counts


def _pick_points(
    db: Session, user: User, goal: Goal, kind: str, kp_id: Optional[int], count: int
) -> List[KnowledgePoint]:
    points = _leaves(db, goal.id)
    if kp_id is not None:
        children = [point for point in points if point.parent_id == kp_id]
        if children:
            return children[: max(1, min(count, 3))]
        selected = [point for point in points if point.id == kp_id]
        return selected or points[:1]
    mastery = _mastery(db, user.id, goal.id)
    mistakes = _mistake_counts(db, user.id, goal.id)
    if kind == "probe":
        ordered = sorted(
            points,
            key=lambda point: (mastery.get(point.id, 0.0), -mistakes.get(point.id, 0)),
        )
    elif kind in ("transfer", "mixed"):
        middle = [point for point in points if 0.3 <= mastery.get(point.id, 0.0) <= 0.75]
        ordered = sorted(middle or points, key=lambda point: mastery.get(point.id, 0.0))
    elif kind == "boundary":
        ordered = sorted(
            points,
            key=lambda point: (mistakes.get(point.id, 0), mastery.get(point.id, 0.0)),
        )
    elif kind == "speed":
        ordered = sorted(points, key=lambda point: -mastery.get(point.id, 0.0))
    elif kind == "reverse":
        ordered = sorted(
            points,
            key=lambda point: (-point.weight, mistakes.get(point.id, 0)),
        )
    elif kind == "trap":
        ordered = sorted(points, key=lambda point: -mistakes.get(point.id, 0))
    else:
        ordered = sorted(points, key=lambda point: -point.weight)
    if kind == "mixed" and len(ordered) >= 2:
        return ordered[: max(2, min(count, 3))]
    return ordered[: max(1, min(count, 3))]


def _rule_questions(points: List[KnowledgePoint], kind: str) -> List[dict]:
    questions = []
    for point in points:
        prefix = {
            "probe": "探针题",
            "transfer": "迁移题",
            "challenge": "挑战题",
            "boundary": "边界辨析题",
            "speed": "快答题",
            "reverse": "逆向题",
            "trap": "陷阱题",
            "mixed": "混合题",
        }.get(kind, "题目")
        options = [
            f"「{point.name}」的核心概念",
            f"与「{point.name}」无关的常识",
            f"「{point.name}」的反义概念",
            f"以上都不是",
        ]
        correct = options[0]
        random.shuffle(options)
        questions.append(
            {
                "question": f"{prefix}：「{point.name}」最需要先确认的是哪一项？",
                "options": options,
                "answer_index": options.index(correct),
                "explanation": f"「{point.name}」权重 {point.weight}，当前需要先确认核心概念边界。",
                "kp_name": point.name,
                "kp_id": point.id,
            }
        )
    return questions


async def _llm_questions(points: List[KnowledgePoint], kind: str, goal: Optional[Goal] = None) -> List[dict]:
    exam_name = goal.exam_name if goal else ""
    point_names = [point.name for point in points]
    if not llm.available:
        return []
    names = "、".join(point_names)
    policy = item_policy.subject_policy(exam_name, point_names, mode=kind)
    system = (
        "你是学迹 AI 主动探针出题官。"
        + KIND_BRIEF.get(kind, KIND_BRIEF["probe"])
        + "输出 JSON："
        '{"questions":[{"question":"题干","options":["A","B","C","D"],'
        '"answer_index":0,"explanation":"解析","kp_name":"知识点名称"}]}。'
        "每题恰好 4 个选项、只有一个正确答案；题干必须考学科内容本身，"
        "禁止考学习方法、模块归属或理解方式；题干与选项语言必须符合 subject_policy（数学类中文、英语类英文）；"
        "解析不超过 60 字，kp_name 必须来自给定知识点。只输出 JSON。"
    )
    prompt = f"知识点：{names}。生成 {len(points)} 道题。\n{policy}"
    name_map = {point.name: point for point in points}
    collected: List[dict] = []
    seen: set = set()
    for attempt in range(2):
        attempt_prompt = prompt
        if attempt == 1:
            attempt_prompt += "\n上一次输出不合格（中文题干或学习方法类元问题），请严格按 subject_policy 重写成真实学科题。"
        data = await llm.chat_json(system, attempt_prompt)
        if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
            continue
        for item in data["questions"]:
            if not isinstance(item, dict) or len(collected) >= len(points):
                continue
            options = item.get("options")
            answer_index = item.get("answer_index")
            question = str(item.get("question", "")).strip()
            if not question or not isinstance(options, list) or len(options) != 4:
                continue
            if not isinstance(answer_index, int) or not 0 <= answer_index < 4:
                continue
            option_texts = [str(option)[:120] for option in options]
            point = name_map.get(str(item.get("kp_name", "")).strip()) or points[len(collected) % len(points)]
            if item_policy.item_issues(question, option_texts, exam_name, point_names, kp_name=point.name):
                continue
            key = question.lower()
            if key in seen:
                continue
            seen.add(key)
            collected.append(
                {
                    "question": question,
                    "options": option_texts,
                    "answer_index": answer_index,
                    "explanation": str(item.get("explanation", ""))[:200],
                    "kp_name": point.name,
                    "kp_id": point.id,
                }
            )
        if len(collected) >= len(points):
            break
    return collected[: len(points)]


def probe_to_dict(item: ProbeItem, point_map: Dict[int, KnowledgePoint]) -> dict:
    point = point_map.get(item.kp_id) if item.kp_id else None
    try:
        options = json.loads(item.options)
    except Exception:
        options = []
    return {
        "id": item.id,
        "kind": item.kind,
        "kp_id": item.kp_id,
        "kp_name": point.name if point else None,
        "question": item.question,
        "options": options,
        "status": item.status,
        "correct": item.correct,
        "explanation": item.explanation,
        "created_at": item.created_at,
    }


async def generate_probes(
    db: Session,
    user: User,
    goal: Goal,
    kind: str = "probe",
    count: int = 1,
    kp_id: Optional[int] = None,
) -> List[ProbeItem]:
    if kind not in VALID_KINDS:
        raise ValueError("探针类型必须是 probe / transfer / challenge")
    points = _pick_points(db, user, goal, kind, kp_id, count)
    if not points:
        raise ValueError("还没有知识点，请先导入资料")
    questions = await _llm_questions(points, kind, goal)
    engine = "llm" if questions else "rule"
    if not questions:
        questions = _rule_questions(points, kind)

    created = []
    for question in questions:
        point = next((item for item in points if item.id == question.get("kp_id")), points[0])
        item = ProbeItem(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            kind=kind,
            question=question["question"],
            options=json.dumps(question["options"], ensure_ascii=False),
            answer_index=question["answer_index"],
            explanation=question["explanation"],
            status="pending",
        )
        db.add(item)
        created.append(item)
    db.flush()
    record_evidence(
        db,
        user.id,
        goal.id,
        f"{kind}_generate",
        KIND_BRIEF[kind][:30],
        {
            "points": [point.name for point in points],
            "count": len(created),
            "kind": kind,
        },
        f"生成 {len(created)} 道{KIND_BRIEF[kind][:12]}题",
        engine=engine,
    )
    db.commit()
    for item in created:
        db.refresh(item)
    return created


def submit_probe(db: Session, user: User, goal: Goal, probe: ProbeItem, chosen: int) -> dict:
    if probe.status != "pending":
        raise ValueError("这道题已经作答")
    try:
        options = json.loads(probe.options)
    except Exception:
        options = []
    correct = chosen == probe.answer_index
    probe.status = "answered"
    probe.chosen_index = chosen
    probe.correct = correct
    from datetime import datetime

    probe.answered_at = datetime.utcnow()

    mastery_value = None
    resilience = 0
    if probe.kp_id:
        point = db.get(KnowledgePoint, probe.kp_id)
        if point:
            if probe.kind in TRAINING_KINDS:
                # 训练型题型不惩罚掌握度，答错也记录一次尝试
                record = db.scalar(
                    select(Mastery).where(
                        Mastery.user_id == user.id, Mastery.kp_id == point.id
                    )
                )
                mastery_value = record.value if record else 0.0
                resilience = 2 if correct else 1
            else:
                record = apply_answer(db, user.id, point, correct=correct)
                mastery_value = record.value
                resilience = 2 if correct else 0
    record_evidence(
        db,
        user.id,
        goal.id,
        f"{probe.kind}_answer",
        probe.question[:60],
        {
            "chosen": chosen,
            "correct_index": probe.answer_index,
            "options": options,
            "kind": probe.kind,
            "correct": correct,
        },
        "回答正确" if correct else "回答错误，已记录为盲区证据",
        engine="rule",
    )
    db.commit()
    return {
        "correct": correct,
        "explanation": probe.explanation,
        "mastery": mastery_value,
        "resilience": resilience,
        "evidence": "已写入学习证据链",
    }
