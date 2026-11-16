"""反向教学三件套：费曼检验场 · 反向判卷 · 错误免疫。

三件事共用一条底线：**判定不依赖模型的自由发挥**。

- 费曼：讲解要点在开讲前预置在服务端，评分只做「讲没讲到」的覆盖判定；
- 判卷：错误步骤与错因在出题时写死，批改按 45/30/25 三档规则算分；
- 免疫：诱饵选项与正确选项写死在 trap_key / correct_key，只做键比对。

模型只负责「写题面 / 写要点 / 辅助判命中」，写歪了有结构校验挡回去，
挡不住就回落到规则题；这些回落路径都会在 `engine` 字段里如实标注。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import (
    FeynmanSession,
    Goal,
    ImmuneDrill,
    KnowledgePoint,
    Mastery,
    Mistake,
    ReverseTask,
    User,
)
from .mastery_service import apply_answer
from .rules import MISTAKE_CATEGORIES

# ---------------------------------------------------------------- 公共工具

SYMBOL_MAP = {"≠": "不等于", "≥": "大于等于", "≤": "小于等于", "→": "推出", "±": "正负", "∞": "无穷"}


def _clean(text: Any, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _norm(text: str) -> str:
    t = str(text or "").lower()
    for k, v in SYMBOL_MAP.items():
        t = t.replace(k, v)
    return re.sub(r"[\s，。；、,.;:：!！?？\"'“”‘’()（）\[\]【】]", "", t)


def _coverage(text: str, terms: List[str]) -> Tuple[List[str], List[str]]:
    """规则兜底：只做字符串包含，不猜语义。"""
    body = _norm(text)
    covered, missed = [], []
    for term in terms:
        token = _norm(term)
        if token and token in body:
            covered.append(term)
        else:
            missed.append(term)
    return covered, missed


def _board_of(db: Session, point: Optional[KnowledgePoint]) -> str:
    if point is None:
        return "未归类"
    if point.parent_id:
        parent = db.get(KnowledgePoint, point.parent_id)
        if parent is not None:
            return parent.name
    return point.name


def _recent_kp_ids(db: Session, model, user_id: int, goal_id: int, limit: int = 6) -> List[int]:
    rows = db.execute(
        select(model.kp_id)
        .where(model.user_id == user_id, model.goal_id == goal_id)
        .order_by(model.id.desc())
        .limit(limit)
    ).all()
    return [row[0] for row in rows if row[0]]


def _kp_mistake_counts(db: Session, user_id: int, goal_id: int) -> Dict[int, int]:
    rows = db.execute(
        select(Mistake.kp_id, func.count(Mistake.id))
        .where(Mistake.user_id == user_id, Mistake.goal_id == goal_id, Mistake.kp_id.is_not(None))
        .group_by(Mistake.kp_id)
    ).all()
    return {int(kp_id): int(count) for kp_id, count in rows if kp_id}


# ---------------------------------------------------------------- 一、费曼检验场

GENERIC_POINTS = [
    {"term": "定义", "hint": "它是什么：用一句话把概念说清楚"},
    {"term": "前提条件", "hint": "什么时候成立：定义前面那行「若/当」才是考点"},
    {"term": "用法", "hint": "怎么用：典型的一步操作或公式"},
    {"term": "易错点", "hint": "哪里会翻车：你自己或同学常错的地方"},
    {"term": "与其他知识的联系", "hint": "它和前面学的什么连着"},
]

POINT_SYSTEM = """你是一位教研老师。学生在做「费曼讲解」练习：把知识点讲给外行听。
请为知识点「{kp}」（备考「{exam}」）预置一份【标准讲解要点】——一份合格的讲解必须覆盖的内容。

要求：
1. 4~6 条，每条一个关键词 term（2~10 字，学生讲解时会自然说到的词，如「定义域」「判别式」）+ 一句话 hint。
2. 必须具体到这个知识点本身，不要「认真审题」这类空话。
3. term 会用于覆盖判定：学生讲到了就命中，所以要选讲解里自然会出现的关键词。

只输出 JSON，不要解释：
{{"points":[{{"term":"...","hint":"..."}}]}}"""


def _normalize_points(data: Any) -> Optional[List[dict]]:
    if not isinstance(data, dict):
        return None
    out = []
    for item in data.get("points") or []:
        if not isinstance(item, dict):
            continue
        term = _clean(item.get("term"), 16)
        hint = _clean(item.get("hint"), 80)
        if 2 <= len(term) <= 12:
            out.append({"term": term, "hint": hint or "讲清楚这一点"})
    return out if len(out) >= 3 else None


def _points_from_children(db: Session, point: KnowledgePoint) -> Optional[List[dict]]:
    children = db.scalars(
        select(KnowledgePoint)
        .where(KnowledgePoint.parent_id == point.id)
        .order_by(KnowledgePoint.weight.desc())
        .limit(6)
    ).all()
    if len(children) < 3:
        return None
    return [{"term": c.name[:12], "hint": f"讲清楚「{c.name}」是什么、怎么用"} for c in children]


async def _build_points(db: Session, goal: Goal, point: KnowledgePoint) -> Tuple[List[dict], str]:
    """预置标准讲解要点：模型 → 图谱子节点 → 通用骨架。"""
    if llm.available:
        data = await llm.chat_json(
            POINT_SYSTEM.format(kp=point.name, exam=goal.exam_name),
            f"请为「{point.name}」生成标准讲解要点。",
            temperature=0.4,
            max_tokens=600,
            prompt_id="feynman.points",
        )
        points = _normalize_points(data)
        if points:
            return points, "llm"
    children = _points_from_children(db, point)
    if children:
        return children, "graph"
    return [dict(p) for p in GENERIC_POINTS], "rule"


def _pick_feynman_kp(
    db: Session, user: User, goal: Goal, kp_id: Optional[int]
) -> Tuple[KnowledgePoint, str]:
    if kp_id:
        point = db.get(KnowledgePoint, kp_id)
        if not point or point.goal_id != goal.id:
            raise ValueError("知识点不存在")
        return point, "你主动指定的知识点"

    counts = _kp_mistake_counts(db, user.id, goal.id)
    rows = db.execute(
        select(Mastery, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePoint.id == Mastery.kp_id)
        .where(Mastery.user_id == user.id, KnowledgePoint.goal_id == goal.id)
    ).all()
    candidates = [(m, kp) for m, kp in rows if m.value >= 0.5 and (counts.get(kp.id, 0) > 0 or m.value >= 0.7)]
    candidates.sort(key=lambda pair: (-pair[0].value, -counts.get(pair[1].id, 0)))

    used = _recent_kp_ids(db, FeynmanSession, user.id, goal.id)
    candidates.sort(key=lambda pair: (pair[1].id in used, -pair[0].value))

    if candidates:
        m, point = candidates[0]
        wrong = counts.get(point.id, 0)
        if point.id in used:
            reason = "换一个讲过的知识点，避免只在同一个点上找感觉"
        elif wrong:
            reason = (
                f"自测掌握分 {round(m.value * 100)} 分、但错过 {wrong} 题——"
                "「以为会了」最浓的地方，讲一遍就知道是不是真的会"
            )
        else:
            reason = f"自测掌握分 {round(m.value * 100)} 分，正好检验是不是「看懂了」的假熟"
        return point, reason

    point = db.scalar(
        select(KnowledgePoint)
        .where(KnowledgePoint.goal_id == goal.id)
        .order_by(KnowledgePoint.weight.desc())
    )
    if not point:
        raise ValueError("这个目标还没有知识点，先导入大纲")
    return point, "还没有自测数据，先挑了权重最高的知识点"


async def start_feynman(db: Session, user: User, goal: Goal, kp_id: Optional[int] = None) -> Dict[str, Any]:
    point, reason = _pick_feynman_kp(db, user, goal, kp_id)
    points, engine = await _build_points(db, goal, point)

    row = FeynmanSession(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=point.id,
        kp_name=point.name,
        pick_reason=reason,
        points=json.dumps(points, ensure_ascii=False),
        points_engine=engine,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "session_id": row.id,
        "kp_id": point.id,
        "kp_name": point.name,
        "reason": reason,
        "engine": engine,
        "min_chars": 30,
        "max_chars": 1500,
        "prompt": f"用两三句话把「{point.name}」讲给一个没学过的人听：它是什么、怎么用、哪里容易错。",
        "disclaimer": "讲解要点在服务端，讲完按「讲没讲到」逐条核对；漏掉的就是你的盲区。",
    }


def _feynman_insight(
    db: Session, user_id: int, goal_id: int, point: Optional[KnowledgePoint], missed: List[str]
) -> str:
    if point is None:
        return ""
    mistakes = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user_id,
            Mistake.goal_id == goal_id,
            Mistake.kp_id == point.id,
        )
    ).all()
    if not mistakes:
        return ""
    causes: Dict[str, int] = {}
    for item in mistakes:
        label = item.category_label or MISTAKE_CATEGORIES.get(item.category, "概念不清")
        causes[label] = causes.get(label, 0) + 1
    top = max(causes, key=causes.get) if causes else ""
    base = f"这个知识点你累计错了 {len(mistakes)} 题"
    return f"{base}，主要错因是「{top}」。" if top else base + "。"


async def submit_feynman(
    db: Session, user: User, session_id: int, speech: str, speech_mode: str = "text"
) -> Dict[str, Any]:
    row = db.get(FeynmanSession, session_id)
    if not row or row.user_id != user.id:
        raise ValueError("讲解会话不存在")
    if row.submitted:
        raise ValueError("这次讲解已经核对过了，换一个知识点再讲一次")
    text = (speech or "").strip()
    if len(text) < 30:
        raise ValueError("讲解太短了：至少写两三句话，讲出「它是什么、什么时候成立、怎么用」")

    points = json.loads(row.points or "[]")
    terms = [p["term"] for p in points]
    covered, missed = _coverage(text, terms)
    engine = "rule"
    suspects: List[str] = []

    if llm.available and missed:
        data = await llm.chat_json(
            "你是讲解核对助手。给定「标准讲解要点」清单和学生的一段讲解，做两件事：\n"
            "1. 判断讲解里是否提到了每个要点：同义表达、符号不同写法、换说法都算提到；只沾边不算。\n"
            "2. 摘出讲解里明确说错的原句（与教科书结论矛盾），最多 1 条；含糊、不严谨的不算，没有就给空数组。\n"
            '只输出 JSON：{"covered":["原样引用清单里的要点"],"suspects":["讲解原文"]}',
            f"要点清单：{json.dumps(terms, ensure_ascii=False)}\n学生讲解：{text[:1200]}",
            max_tokens=500,
            prompt_id="feynman.judge",
        )
        if isinstance(data, dict) and isinstance(data.get("covered"), list):
            said = {_norm(item) for item in data["covered"]}
            hit = [t for t in terms if _norm(t) in said]
            if hit:
                covered = hit
                missed = [t for t in terms if t not in hit]
                engine = "llm"
            suspects = [_clean(item, 120) for item in (data.get("suspects") or []) if _clean(item, 120)][:1]

    coverage = round(len(covered) / max(1, len(terms)), 3)
    if coverage >= 0.85:
        verdict = "讲得很好：要点全覆盖，这个点你是真的会了"
    elif coverage >= 0.5:
        verdict = "讲了主干，漏了关键处——漏掉的那几条恰恰是考试最爱考的"
    else:
        verdict = "讲不全：你以为的「会」目前还停留在「眼熟」，看下面的漏项"

    point = db.get(KnowledgePoint, row.kp_id) if row.kp_id else None
    insight = _feynman_insight(db, user.id, row.goal_id, point, missed)
    mastery = (
        db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id))
        if point
        else None
    )
    if missed and mastery is not None and mastery.value >= 0.6:
        insight = (insight + " " if insight else "") + (
            f"注意：你的自测掌握分是 {round(mastery.value * 100)} 分，但这次只讲出 "
            f"{len(covered)}/{len(terms)} 条要点——这就是熟练度错觉：眼熟不等于会讲，会讲不等于会用。"
        )

    row.speech = text[:2000]
    row.speech_mode = speech_mode if speech_mode in ("text", "voice") else "text"
    row.coverage = coverage
    row.covered = json.dumps(covered, ensure_ascii=False)
    row.missed = json.dumps(missed, ensure_ascii=False)
    row.suspects = json.dumps(suspects, ensure_ascii=False)
    row.insight = insight
    row.engine = engine
    row.submitted = True
    db.commit()

    hint_map = {p["term"]: p["hint"] for p in points}
    return {
        "session_id": row.id,
        "kp_name": row.kp_name,
        "coverage": coverage,
        "covered": covered,
        "missed": [{"term": t, "hint": hint_map.get(t, "")} for t in missed],
        "suspects": suspects,
        "suspects_note": "以下原句表述疑似有问题，仅供参考、不参与计分，请自行核对教材：" if suspects else "",
        "verdict": verdict,
        "insight": insight,
        "engine": engine,
        "speech_mode": row.speech_mode,
    }


def feynman_profile(db: Session, user: User, goal: Goal) -> Dict[str, Any]:
    rows = db.scalars(
        select(FeynmanSession)
        .where(
            FeynmanSession.user_id == user.id,
            FeynmanSession.goal_id == goal.id,
            FeynmanSession.submitted.is_(True),
        )
        .order_by(FeynmanSession.id.desc())
        .limit(60)
    ).all()

    per_kp: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if not row.kp_id:
            continue
        agg = per_kp.setdefault(row.kp_id, {"kp_id": row.kp_id, "kp_name": row.kp_name, "n": 0, "cov": 0.0})
        agg["n"] += 1
        agg["cov"] += row.coverage

    items = []
    for agg in per_kp.values():
        mastery = db.scalar(
            select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == agg["kp_id"])
        )
        value = round(mastery.value, 3) if mastery else None
        cov = round(agg["cov"] / agg["n"], 3)
        items.append(
            {
                "kp_id": agg["kp_id"],
                "kp_name": agg["kp_name"],
                "sessions": agg["n"],
                "avg_coverage": cov,
                "mastery": value,
                "gap": round(value - cov, 3) if value is not None else None,
            }
        )
    items.sort(key=lambda item: (-(item["gap"] if item["gap"] is not None else -9), item["avg_coverage"]))

    illusions = [item for item in items if (item["gap"] or 0) >= 0.2 and item["sessions"] >= 2][:5]
    attempts = len(rows)
    avg_cov = round(sum(r.coverage for r in rows) / attempts, 3) if attempts else None

    if illusions:
        top = illusions[0]
        insight = (
            f"「{top['kp_name']}」你自测 {round(100 * (top['mastery'] or 0))} 分、讲出来只有 "
            f"{round(100 * top['avg_coverage'])}%——最典型的熟练度错觉，考试最容易在这里翻车。"
        )
    elif attempts >= 2:
        insight = "讲解覆盖和自测分基本一致：目前没有明显的「假熟」，继续保持先讲再做的习惯。"
    elif attempts:
        insight = "样本还少（少于 2 次核对），以下只是探索性参考，不下结论。"
    else:
        insight = "还没有讲解记录：挑一个「看着会」的知识点，讲 60 秒试试。"

    return {
        "attempts": attempts,
        "avg_coverage": avg_cov,
        "items": items[:10],
        "illusions": illusions,
        "insight": insight,
        "sample_state": "ok" if attempts >= 2 else ("exploratory" if attempts else "empty"),
    }


def feynman_history(db: Session, user: User, goal: Goal, limit: int = 10) -> List[Dict[str, Any]]:
    rows = db.scalars(
        select(FeynmanSession)
        .where(
            FeynmanSession.user_id == user.id,
            FeynmanSession.goal_id == goal.id,
            FeynmanSession.submitted.is_(True),
        )
        .order_by(FeynmanSession.id.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    return [
        {
            "id": row.id,
            "kp_name": row.kp_name,
            "coverage": row.coverage,
            "covered": json.loads(row.covered or "[]"),
            "missed": json.loads(row.missed or "[]"),
            "speech_mode": row.speech_mode,
            "insight": row.insight,
            "day": row.created_at.date().isoformat(),
        }
        for row in rows
    ]


# ---------------------------------------------------------------- 二、反向判卷

GRADE_CAUSES = ["概念不清", "方法不会", "粗心"]

GRADER_SYSTEM = """你是一位命题老师，同时要扮演一个「犯了典型错误的学生」，为备考「{exam}」的学生
准备一份【待批改的答卷】。目标知识点：{kp}，难度：{difficulty}。

要求：
1. 先出一道有明确解题过程的小题（1~2 问，不要选择题），再给出 3~5 个步骤的解答。
2. 解答中只能有一处错误，必须落在某一步（error_step 从 1 开始）。
3. 错误类型固定为「{want_type}」：
   - 概念不清：混淆定义 / 条件 / 适用边界，把结论用在不适用的地方
   - 方法不会：步骤缺失、方法选错、该分类讨论没讨论
   - 粗心：符号、单位、计算、抄错、漏看条件
   错误要真实，是学生真的会犯的，不是随便改个数字。
4. 给出 correct_step（这一步应该怎么写，具体到可执行）与 key_terms（修正时必须提到的 2~4 个关键词，每个 2~8 字）。
5. 题干里不要暗示哪一步错了。

只输出 JSON，不要解释：
{{"question":"题干","steps":[{{"no":1,"text":"..."}}],"error_step":3,
"error_type":"{want_type}","correct_step":"...","key_terms":["...","..."],
"why":"学生为什么会这么错，40字内","answer":"最终答案"}}"""


def _normalize_task(data: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    steps = []
    for item in data.get("steps") or []:
        text = _clean(item.get("text"), 300) if isinstance(item, dict) else _clean(item, 300)
        if text:
            steps.append({"no": len(steps) + 1, "text": text})
    if len(steps) < 3:
        return None
    try:
        err = int(data.get("error_step") or 0)
    except (TypeError, ValueError):
        return None
    if not 1 <= err <= len(steps):
        return None
    etype = _clean(data.get("error_type"), 8)
    if etype not in GRADE_CAUSES:
        etype = "概念不清"
    terms = [_clean(t, 12) for t in (data.get("key_terms") or []) if _clean(t, 12)]
    if not terms:
        return None
    return {
        "question": _clean(data.get("question"), 600),
        "steps": steps,
        "error_step": err,
        "error_type": etype,
        "correct_step": _clean(data.get("correct_step"), 400),
        "key_terms": terms[:4],
        "why": _clean(data.get("why"), 80),
        "answer": _clean(data.get("answer"), 200),
    }


def _fallback_task(kp_name: str, cause: str) -> Dict[str, Any]:
    return {
        "question": (
            f"下面是一份关于「{kp_name}」的作答，请判断并说明理由："
            f"「{kp_name} 只在标准情形下成立，所以只要按标准情形套用就不会错。」"
        ),
        "steps": [
            {"no": 1, "text": f"读题：要判断的是「{kp_name}」的适用范围这一说法是否成立。"},
            {"no": 2, "text": f"回忆教材里「{kp_name}」的定义，以及定义前面写的前提条件。"},
            {"no": 3, "text": f"结论：该说法成立，因为「{kp_name}」本来就是标准情形下的结论，套用即可。"},
            {"no": 4, "text": "作答：说法正确。"},
        ],
        "error_step": 3,
        "error_type": cause if cause in GRADE_CAUSES else "概念不清",
        "correct_step": (
            f"第 3 步不能直接下结论：要先写出「{kp_name}」的前提条件，说明它在什么条件下成立、"
            "什么条件下失效（举一个反例），再说适用范围。"
        ),
        "key_terms": ["前提条件", "反例", "适用范围"],
        "why": "只记住了结论，没记住结论成立的前提——这是最典型的「以为会了」。",
        "answer": "说法不成立，需说明前提条件与反例。",
    }


def _pick_reverse_kp(
    db: Session, user: User, goal: Goal, kp_id: Optional[int]
) -> Tuple[KnowledgePoint, str]:
    if kp_id:
        point = db.get(KnowledgePoint, kp_id)
        if not point or point.goal_id != goal.id:
            raise ValueError("知识点不存在")
        return point, "你主动指定的知识点"

    counts = _kp_mistake_counts(db, user.id, goal.id)
    rows = db.execute(
        select(Mastery, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePoint.id == Mastery.kp_id)
        .where(Mastery.user_id == user.id, KnowledgePoint.goal_id == goal.id)
    ).all()
    scored = [(m, kp) for m, kp in rows]
    scored.sort(key=lambda pair: (-counts.get(pair[1].id, 0), pair[0].value))
    used = _recent_kp_ids(db, ReverseTask, user.id, goal.id)
    scored.sort(key=lambda pair: pair[1].id in used)

    if scored:
        m, point = scored[0]
        wrong = counts.get(point.id, 0)
        if wrong:
            return point, f"挑了你错得最多的「{point.name}」：{wrong} 道错题在这里"
        return point, f"暂时没有明显盲区，挑了掌握度最低的「{point.name}」（{round(m.value * 100)}%）"

    point = db.scalar(
        select(KnowledgePoint)
        .where(KnowledgePoint.goal_id == goal.id)
        .order_by(KnowledgePoint.weight.desc())
    )
    if not point:
        raise ValueError("这个目标还没有知识点，先导入大纲")
    return point, "挑了权重最高的知识点"


async def start_reverse(
    db: Session,
    user: User,
    goal: Goal,
    kp_id: Optional[int] = None,
    difficulty: str = "normal",
    cause: Optional[str] = None,
) -> Dict[str, Any]:
    point, reason = _pick_reverse_kp(db, user, goal, kp_id)

    if cause not in GRADE_CAUSES:
        done = db.scalar(
            select(func.count(ReverseTask.id)).where(
                ReverseTask.user_id == user.id, ReverseTask.goal_id == goal.id
            )
        ) or 0
        cause = GRADE_CAUSES[int(done) % len(GRADE_CAUSES)]

    data = None
    engine = "rule"
    if llm.available:
        data = _normalize_task(
            await llm.chat_json(
                GRADER_SYSTEM.format(exam=goal.exam_name, kp=point.name, difficulty=difficulty, want_type=cause),
                f"请为「{point.name}」准备一份待批改的答卷，错误类型：{cause}。",
                temperature=0.7,
                max_tokens=1200,
                prompt_id="reverse.task",
            )
        )
        if data:
            engine = "llm"
    if not data:
        data = _fallback_task(point.name, cause)
        engine = "rule"

    row = ReverseTask(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=point.id,
        kp_name=point.name,
        question=data["question"],
        steps=json.dumps(data["steps"], ensure_ascii=False),
        error_step=data["error_step"],
        error_type=data["error_type"],
        correct_step=data["correct_step"],
        key_terms=json.dumps(data["key_terms"], ensure_ascii=False),
        why=data["why"],
        answer=data["answer"],
        engine=engine,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "task_id": row.id,
        "kp_id": point.id,
        "kp_name": point.name,
        "question": row.question,
        "steps": data["steps"],
        "engine": engine,
        "reason": reason,
        "cause_options": GRADE_CAUSES,
        "disclaimer": "这份答卷只有一处错，可能在任何一步；错误是出题时预置的，所以你的批改会被确定性核对。",
    }


def _lesson(detail: Dict[str, Any]) -> str:
    if not detail["position"]["ok"]:
        if detail["position"]["near"]:
            return "位置差了一步：你注意到了问题，但没定位到具体那一步——真实考试里这一步就丢分了。"
        return "先别急着判断错因：把相邻两步连起来读，找「结论和条件对不上」的地方。"
    if not detail["type"]["ok"]:
        return "位置找对了，但错因说错——说明你知道这里不对，却说不出为什么不对。这类错自己犯了也很难改。"
    if detail["fix"]["missed"]:
        return f"只差修正要点：补上「{'、'.join(detail['fix']['missed'])}」，就是完整的一次纠错。"
    return "定位、错因、修正全对——你已经具备「自己给自己批卷」的能力。"


async def _judge_fix(fix_text: str, terms: List[str]) -> Tuple[List[str], List[str], str]:
    if not (fix_text or "").strip():
        return [], list(terms), "rule"
    covered, missed = _coverage(fix_text, terms)
    if covered or not llm.available:
        return covered, missed, "rule"
    data = await llm.chat_json(
        "你是判卷助手。给定「必须提到的要点」清单，判断用户写的修正说明里是否提到了每一个要点。\n"
        "同义表达、符号不同写法、换行分段都算提到；只沾边不算。\n"
        '只输出 JSON：{"covered":["原样引用清单里的要点"]}',
        f"要点清单：{json.dumps(terms, ensure_ascii=False)}\n用户修正说明：{fix_text[:600]}",
        max_tokens=300,
        prompt_id="reverse.judge",
    )
    if not isinstance(data, dict) or not isinstance(data.get("covered"), list):
        return covered, missed, "rule"
    said = {_norm(item) for item in data["covered"]}
    hit = [t for t in terms if _norm(t) in said]
    if not hit:
        return covered, missed, "rule"
    return hit, [t for t in terms if t not in hit], "llm"


async def grade_reverse(
    db: Session, user: User, task_id: int, picked_step: int, picked_type: str, fix_text: str
) -> Dict[str, Any]:
    task = db.get(ReverseTask, task_id)
    if not task or task.user_id != user.id:
        raise ValueError("待批改的答卷不存在")
    if task.graded:
        raise ValueError("这份答卷已经批改过了，换一份新的再来")

    steps = json.loads(task.steps or "[]")
    terms = json.loads(task.key_terms or "[]")
    step_ok = picked_step == task.error_step
    near = (not step_ok) and abs(picked_step - task.error_step) == 1

    pos_pts = 45 if step_ok else (15 if near else 0)
    type_pts = 30 if _clean(picked_type, 8) == task.error_type else 0
    covered, missed, fix_engine = await _judge_fix(fix_text, terms)
    fix_pts = round(25 * len(covered) / max(1, len(terms)))

    score = pos_pts + type_pts + fix_pts
    if score >= 85:
        verdict, tier = "抓到了：定位、错因、修正三样都准", "excellent"
    elif step_ok and type_pts and fix_pts:
        verdict, tier = "定位和错因都对，修正还差关键要点", "partial"
    elif step_ok and type_pts:
        verdict, tier = "定位和错因都对，修正没写到点上——知道该改哪，但说不清改成什么", "partial"
    elif step_ok:
        verdict, tier = "位置找对了，但错因说错：你知道这里不对，却说不清为什么不对", "weak"
    elif near and type_pts:
        verdict, tier = "差一步：错因判断准了，位置停在相邻那一步", "weak"
    elif near:
        verdict, tier = "差一步：方向对了，但没定位到具体那一步", "weak"
    elif type_pts:
        verdict, tier = "错因判断准了，但位置找错——这类错自己犯了也容易漏看", "weak"
    else:
        verdict, tier = "没抓到：这份错比你想象的隐蔽，看下面的对照", "miss"

    detail = {
        "position": {"ok": step_ok, "near": near, "expected": task.error_step, "picked": picked_step, "points": pos_pts},
        "type": {"ok": type_pts > 0, "expected": task.error_type, "picked": picked_type, "points": type_pts},
        "fix": {"covered": covered, "missed": missed, "points": fix_pts, "total_terms": len(terms), "engine": fix_engine},
        "engine": task.engine,
    }
    task.picked_step = picked_step
    task.picked_type = _clean(picked_type, 16)
    task.fix_text = _clean(fix_text, 1000)
    task.score = float(score)
    task.detail = json.dumps(detail, ensure_ascii=False)
    task.graded = True

    # 判对了就是一次「发现错误」的证据：记一条答对，判错记一条答错
    point = db.get(KnowledgePoint, task.kp_id) if task.kp_id else None
    if point is not None:
        apply_answer(db, user.id, point, score >= 55, question_type="grade", evidence_weight=0.5)
    db.commit()

    return {
        "task_id": task.id,
        "score": score,
        "tier": tier,
        "verdict": verdict,
        "breakdown": detail,
        "truth": {
            "error_step": task.error_step,
            "error_type": task.error_type,
            "wrong_step_text": next((s["text"] for s in steps if s["no"] == task.error_step), ""),
            "correct_step": task.correct_step,
            "key_terms": terms,
            "why": task.why,
            "answer": task.answer,
        },
        "lesson": _lesson(detail),
    }


def _rate(values: List[bool]) -> Optional[float]:
    return round(sum(1 for v in values if v) / len(values), 3) if values else None


def reverse_profile(db: Session, user: User, goal: Goal) -> Dict[str, Any]:
    rows = db.scalars(
        select(ReverseTask)
        .where(
            ReverseTask.user_id == user.id,
            ReverseTask.goal_id == goal.id,
            ReverseTask.graded.is_(True),
        )
        .order_by(ReverseTask.id.desc())
        .limit(60)
    ).all()

    attempts = len(rows)
    avg = round(sum(r.score for r in rows) / attempts, 1) if attempts else None
    pos_hits = [r.picked_step == r.error_step for r in rows]
    type_hits = [r.picked_type == r.error_type for r in rows]
    perfect = [r.score >= 85 for r in rows]

    by_type = []
    for cause in GRADE_CAUSES:
        subset = [r for r in rows if r.error_type == cause]
        by_type.append(
            {
                "cause": cause,
                "total": len(subset),
                "detected": sum(1 for r in subset if r.picked_type == cause),
                "rate": _rate([r.picked_type == cause for r in subset]),
            }
        )

    since = datetime.utcnow() - timedelta(days=90)
    mistakes = db.scalars(
        select(Mistake).where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= since,
        )
    ).all()
    own = {label: 0 for label in MISTAKE_CATEGORIES.values()}
    for item in mistakes:
        label = item.category_label or MISTAKE_CATEGORIES.get(item.category, "概念不清")
        if label in own:
            own[label] += 1
    own_total = sum(own.values())
    own_dist = [
        {"cause": label, "count": count, "share": round(count / own_total, 3) if own_total else 0.0}
        for label, count in own.items()
    ]

    insight = None
    blind_type = None
    if attempts >= 3 and own_total >= 3:
        dominant = max(GRADE_CAUSES, key=lambda c: own.get(c, 0))
        stat = next(item for item in by_type if item["cause"] == dominant)
        if own.get(dominant, 0) > 0 and stat["rate"] is not None and stat["rate"] < 0.5:
            blind_type = dominant
            insight = (
                f"你近 90 天有 {round(100 * own[dominant] / own_total)}% 的错是「{dominant}」，"
                f"但判卷时这类错你只发现 {stat['detected']}/{stat['total']} 次。"
                "也就是说：这类错你自己犯了，很可能也看不出来。"
            )
        elif own.get(dominant, 0) > 0 and stat["rate"] is not None:
            insight = (
                f"你最常犯「{dominant}」，而这类错你判卷时能发现 {stat['detected']}/{stat['total']} 次——"
                "对它的警觉度够，问题更多在「做的时候没停下来」。"
            )
    elif attempts:
        insight = "样本还少（少于 3 次判卷或缺错题记录），先按探索性参考，不下结论。"
    else:
        insight = "还没有判卷记录：先让 AI 交一份带错的答卷，你来当老师。"

    return {
        "attempts": attempts,
        "avg_score": avg,
        "position_rate": _rate(pos_hits),
        "type_rate": _rate(type_hits),
        "perfect_rate": _rate(perfect),
        "by_type": by_type,
        "own_causes": own_dist,
        "own_total": own_total,
        "blind_type": blind_type,
        "insight": insight,
        "sample_state": "ok" if attempts >= 3 else ("exploratory" if attempts else "empty"),
        "disclaimer": "辨别力是「能不能发现错误」的指标，不等于考试分数；少于 3 次判卷只作探索性参考。",
    }


def reverse_history(db: Session, user: User, goal: Goal, limit: int = 10) -> List[Dict[str, Any]]:
    rows = db.scalars(
        select(ReverseTask)
        .where(
            ReverseTask.user_id == user.id,
            ReverseTask.goal_id == goal.id,
            ReverseTask.graded.is_(True),
        )
        .order_by(ReverseTask.id.desc())
        .limit(max(1, min(limit, 30)))
    ).all()
    return [
        {
            "id": row.id,
            "kp_name": row.kp_name,
            "score": row.score,
            "error_type": row.error_type,
            "picked_type": row.picked_type,
            "picked_step": row.picked_step,
            "error_step": row.error_step,
            "day": row.created_at.date().isoformat(),
        }
        for row in rows
    ]


# ---------------------------------------------------------------- 三、错误免疫

GUARD_TARGET = 3
DECAY_DAYS = 14

STATUS_LABEL = {
    "naive": "未接种",
    "building": "建立中",
    "immune": "已免疫",
    "relapse": "复发预警",
    "weak": "抗体偏弱",
}

IMMUNE_SYSTEM = """你是一位擅长设计「陷阱题」的命题老师。学生在备考「{exam}」，
板块是「{board}」，具体考点是「{kp}」，他反复犯的错因是「{cause}」。

请出一道单选题（4 个选项，只有一个正确）：

1. 题面必须短（题干 80 字内），能在一分钟内答完。
2. 必须有一个**诱饵选项**：它看起来对，但正是「{cause}」这类错的典型表现，会把人骗进去。
3. 其余两个选项是明显但不离谱的干扰项，不要写「以上都不对」。
4. 给出 trap_reason（这个诱饵为什么能骗到这类人，40 字内）与 why（正确选项的理由，60 字内）。

只输出 JSON，不要解释：
{{"question":"题干","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},
{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],
"correct_key":"B","trap_key":"C","trap_reason":"...","why":"..."}}"""


def _normalize_drill(data: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    options = []
    for item in data.get("options") or []:
        if not isinstance(item, dict):
            continue
        key = _clean(item.get("key"), 2).upper()
        text = _clean(item.get("text"), 160)
        if key and text:
            options.append({"key": key, "text": text})
    if len(options) != 4 or len({o["key"] for o in options}) != 4:
        return None
    if len({o["text"] for o in options}) != 4:
        return None
    correct = _clean(data.get("correct_key"), 2).upper()
    trap = _clean(data.get("trap_key"), 2).upper()
    keys = {o["key"] for o in options}
    if correct not in keys or trap not in keys or correct == trap:
        return None
    return {
        "question": _clean(data.get("question"), 300),
        "options": options,
        "correct_key": correct,
        "trap_key": trap,
        "trap_reason": _clean(data.get("trap_reason"), 120),
        "why": _clean(data.get("why"), 200),
    }


def fingerprints(db: Session, user: User, goal: Goal) -> Dict[str, Any]:
    """错误指纹：错因 × 知识板块，同一格出现 ≥2 次才算。纯计数，不猜心理。"""
    mistakes = db.scalars(
        select(Mistake).where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
    ).all()
    groups: Dict[str, Dict[str, Any]] = {}
    for item in mistakes:
        label = item.category_label or MISTAKE_CATEGORIES.get(item.category, "概念不清")
        point = db.get(KnowledgePoint, item.kp_id) if item.kp_id else None
        board = _board_of(db, point)
        key = f"{label}|{board}"
        agg = groups.setdefault(
            key,
            {
                "fingerprint": key,
                "cause": label,
                "board": board,
                "count": 0,
                "last_mistake_id": None,
                "last_day": "",
                "kp_ids": [],
            },
        )
        agg["count"] += 1
        if item.kp_id and item.kp_id not in agg["kp_ids"]:
            agg["kp_ids"].append(item.kp_id)
        if agg["last_mistake_id"] is None or item.id > agg["last_mistake_id"]:
            agg["last_mistake_id"] = item.id
            agg["last_day"] = item.created_at.date().isoformat()

    # 每个指纹的接种进度
    drills = db.scalars(
        select(ImmuneDrill)
        .where(ImmuneDrill.user_id == user.id, ImmuneDrill.goal_id == goal.id)
        .order_by(ImmuneDrill.id.desc())
    ).all()
    by_fp: Dict[str, List[ImmuneDrill]] = {}
    for row in drills:
        by_fp.setdefault(row.fingerprint, []).append(row)

    items = []
    for key, agg in groups.items():
        rows = by_fp.get(key, [])
        answered = [r for r in rows if r.answered]
        guards = 0
        for row in answered[:GUARD_TARGET]:
            if row.outcome != "guard":
                break
            guards += 1
        last = answered[0] if answered else None
        decay = False
        if last is not None:
            decay = (datetime.utcnow() - last.created_at).days >= DECAY_DAYS
        if guards >= GUARD_TARGET and not decay:
            status = "immune"
        elif last is not None and last.outcome == "relapse":
            status = "relapse"
        elif guards > 0:
            status = "weak" if decay else "building"
        elif last is not None and last.outcome == "miss":
            status = "weak"
        else:
            status = "naive"
        items.append(
            {
                **agg,
                "drills": len(rows),
                "guards": guards,
                "status": status,
                "status_label": STATUS_LABEL[status],
                "last_practiced": last.created_at.date().isoformat() if last else "",
                "decayed": decay,
            }
        )

    items = [item for item in items if item["count"] >= 2]
    items.sort(key=lambda item: (-item["count"], item["board"]))
    return {
        "items": items,
        "total": len(items),
        "immune": sum(1 for item in items if item["status"] == "immune"),
        "relapse": sum(1 for item in items if item["status"] == "relapse"),
        "guard_target": GUARD_TARGET,
        "decay_days": DECAY_DAYS,
        "note": "指纹是「错因 × 板块」的计数事实，同一格出现 2 次以上才立项，不猜心理、不做诊断。",
    }


def _replay_drill(db: Session, item: Mistake, fingerprint: str, cause: str, board: str) -> Dict[str, Any]:
    """模型不可用 / 输出不合格时的兜底：把用户自己的原题重演一遍，连模型都不需要。"""
    correct = (item.correct_answer or "").strip()
    wrong = (item.user_answer or "").strip()
    if not correct:
        raise ValueError("这条错题缺少正确答案，换一个指纹试试")
    if not wrong or wrong == correct:
        wrong = "（当时没写 / 写了一半）"
    options = [
        {"key": "A", "text": correct[:160]},
        {"key": "B", "text": wrong[:160]},
        {"key": "C", "text": "先跳过，等老师讲"},
        {"key": "D", "text": "这题条件不足，无法判断"},
    ]
    return {
        "question": f"原题重演：{(item.question or '这道题')[:200]}",
        "options": options,
        "correct_key": "A",
        "trap_key": "B",
        "trap_reason": "B 是你当时写下的答案——同一个诱饵，看你这次会不会再咬。",
        "why": (item.suggestion or "回到定义与前提条件，再检查一次每一步的依据。")[:200],
    }


async def make_drill(
    db: Session, user: User, goal: Goal, fingerprint: Optional[str] = None, kp_id: Optional[int] = None
) -> Dict[str, Any]:
    stats = fingerprints(db, user, goal)
    items = stats["items"]
    if fingerprint:
        target = next((item for item in items if item["fingerprint"] == fingerprint), None)
        if target is None:
            raise ValueError("这个错误指纹还没成立：同一类错至少出现 2 次才能接种")
    elif items:
        # 优先复发预警，再优先没练过的
        order = {"relapse": 0, "naive": 1, "weak": 2, "building": 3, "immune": 4}
        target = sorted(items, key=lambda item: (order.get(item["status"], 9), -item["count"]))[0]
    else:
        target = None

    if target is None:
        # 没有指纹时，用指定知识点或错得最多的知识点做一次「通用接种」
        point = db.get(KnowledgePoint, kp_id) if kp_id else None
        if point is None:
            counts = _kp_mistake_counts(db, user.id, goal.id)
            if counts:
                point = db.get(KnowledgePoint, max(counts, key=counts.get))
            else:
                point = db.scalar(
                    select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id).order_by(KnowledgePoint.weight.desc())
                )
        if point is None:
            raise ValueError("这个目标还没有知识点")
        target = {
            "fingerprint": f"概念不清|{_board_of(db, point)}",
            "cause": "概念不清",
            "board": _board_of(db, point),
            "count": 0,
            "last_mistake_id": None,
            "kp_ids": [point.id],
        }

    kp = db.get(KnowledgePoint, target["kp_ids"][0]) if target.get("kp_ids") else None
    kp_name = kp.name if kp else target["board"]

    data = None
    engine = "rule"
    if llm.available:
        data = _normalize_drill(
            await llm.chat_json(
                IMMUNE_SYSTEM.format(
                    exam=goal.exam_name, board=target["board"], kp=kp_name, cause=target["cause"]
                ),
                f"为「{target['board']} · {kp_name}」出一道针对「{target['cause']}」的陷阱题。",
                temperature=0.8,
                max_tokens=900,
                prompt_id="immune.drill",
            )
        )
        if data:
            engine = "llm"

    origin_id = target.get("last_mistake_id")
    if not data:
        item = db.get(Mistake, origin_id) if origin_id else None
        if item is None:
            item = db.scalar(
                select(Mistake).where(Mistake.user_id == user.id, Mistake.goal_id == goal.id).order_by(Mistake.id.desc())
            )
        if item is None:
            raise ValueError("还没有错题可以接种：先做几道题，错题出现后这里会自动生成抗原")
        data = _replay_drill(db, item, target["fingerprint"], target["cause"], target["board"])
        engine = "replay"
        origin_id = item.id

    row = ImmuneDrill(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=kp.id if kp else None,
        kp_name=kp_name,
        fingerprint=target["fingerprint"],
        cause=target["cause"],
        board=target["board"],
        question=data["question"],
        options=json.dumps(data["options"], ensure_ascii=False),
        correct_key=data["correct_key"],
        trap_key=data["trap_key"],
        trap_reason=data["trap_reason"],
        why=data["why"],
        origin_mistake_id=origin_id,
        engine=engine,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "drill_id": row.id,
        "fingerprint": row.fingerprint,
        "cause": row.cause,
        "board": row.board,
        "kp_name": row.kp_name,
        "question": row.question,
        "options": data["options"],
        "engine": engine,
        "count": target["count"],
        "note": "一次只能答一次：答完才揭晓哪个选项是诱饵。",
    }


def answer_drill(db: Session, user: User, drill_id: int, picked: str) -> Dict[str, Any]:
    row = db.get(ImmuneDrill, drill_id)
    if not row or row.user_id != user.id:
        raise ValueError("这次接种记录不存在")
    if row.answered:
        raise ValueError("一次训练只能答一次，换一道新的再来")

    key = _clean(picked, 2).upper()
    options = json.loads(row.options or "[]")
    if key not in {item["key"] for item in options}:
        raise ValueError("选项不存在")

    hit_trap = key == row.trap_key
    correct = key == row.correct_key
    outcome = "guard" if correct else ("relapse" if hit_trap else "miss")
    row.picked = key
    row.outcome = outcome
    row.answered = True

    point = db.get(KnowledgePoint, row.kp_id) if row.kp_id else None
    if point is not None:
        apply_answer(db, user.id, point, correct, question_type="choice", evidence_weight=0.4)
    db.commit()

    answered = db.scalars(
        select(ImmuneDrill)
        .where(
            ImmuneDrill.user_id == user.id,
            ImmuneDrill.goal_id == row.goal_id,
            ImmuneDrill.fingerprint == row.fingerprint,
            ImmuneDrill.answered.is_(True),
        )
        .order_by(ImmuneDrill.id.desc())
    ).all()
    guards = 0
    for item in answered:
        if item.outcome != "guard":
            break
        guards += 1
    if guards >= GUARD_TARGET:
        status = "immune"
    elif outcome == "relapse":
        status = "relapse"
    elif outcome == "guard":
        status = "building"
    else:
        status = "weak"

    trap_text = next((o["text"] for o in options if o["key"] == row.trap_key), "")
    correct_text = next((o["text"] for o in options if o["key"] == row.correct_key), "")
    if correct:
        verdict = "守住了：这次没咬钩"
    elif hit_trap:
        verdict = "中招了：你选的正是这个错因对应的诱饵"
    else:
        verdict = "没选到诱饵，但也不是正确答案：这题的判断依据还没到位"

    return {
        "drill_id": row.id,
        "picked": key,
        "outcome": outcome,
        "verdict": verdict,
        "correct_key": row.correct_key,
        "correct_text": correct_text,
        "trap_key": row.trap_key,
        "trap_text": trap_text,
        "trap_reason": row.trap_reason,
        "why": row.why,
        "guards": guards,
        "guard_target": GUARD_TARGET,
        "status": status,
        "status_label": STATUS_LABEL[status],
        "engine": row.engine,
    }


def immune_profile(db: Session, user: User, goal: Goal) -> Dict[str, Any]:
    stats = fingerprints(db, user, goal)
    rows = db.scalars(
        select(ImmuneDrill)
        .where(
            ImmuneDrill.user_id == user.id,
            ImmuneDrill.goal_id == goal.id,
            ImmuneDrill.answered.is_(True),
        )
        .order_by(ImmuneDrill.id.desc())
        .limit(80)
    ).all()
    guards = [r for r in rows if r.outcome == "guard"]
    relapses = [r for r in rows if r.outcome == "relapse"]
    rate = round(len(guards) / len(rows), 3) if rows else None

    history = [
        {
            "id": row.id,
            "fingerprint": row.fingerprint,
            "cause": row.cause,
            "board": row.board,
            "question": row.question[:80],
            "outcome": row.outcome,
            "day": row.created_at.date().isoformat(),
        }
        for row in rows[:12]
    ]
    return {
        **stats,
        "answered": len(rows),
        "guards": len(guards),
        "relapses": len(relapses),
        "guard_rate": rate,
        "history": history,
        "insight": (
            f"已经接种 {len(rows)} 次，守住 {len(guards)} 次（{round(100 * (rate or 0))}%），"
            f"复发 {len(relapses)} 次。已免疫 {stats['immune']} 个指纹。"
            if rows
            else "还没有接种记录：同一类错出现 2 次以上，这里就会出现可接种的抗原。"
        ),
        "disclaimer": "「抗体」只是比喻，不涉及任何医学判断；所有数值都按你自己的训练记录计算。",
    }
