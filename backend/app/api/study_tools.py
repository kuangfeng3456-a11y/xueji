import hashlib
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..cache import cache
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..llm import llm
from ..models import KnowledgePoint, Mastery, QuizAttempt, User
from ..schemas import (
    FlashcardDeckOut,
    FlashcardExplainOut,
    FlashcardReviewIn,
    FlashcardReviewOut,
    QuizGenerateIn,
    QuizGenerateOut,
    QuizResultOut,
    QuizSubmitIn,
)
from ..services.ai_content import ai_flashcard_explanation
from ..services.flashcards import build_deck, review_card
from ..services import question_bank, quiz_material, tiku_bank
from ..services import quiz as quiz_service
from ..services.quiz import (
    cached_bank,
    fetch_external_bank,
    generate_quiz,
    grade_quiz,
    store_bank,
)

router = APIRouter(tags=["闪卡与随堂测"])


@router.get("/goals/{goal_id}/question-banks")
async def question_bank_catalog(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """返回当前目标的题库覆盖与来源状态，不暴露答案或题目缓存。

    「来源」按出题链路的真实优先级判定；自建题库（tikuAdapter）按知识点建课程，
    所以每个知识点能报出「题库站里有几道对应这道知识点的题」。
    """
    goal = get_user_goal(goal_id, user, db)
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids] or points

    tiku_counts = await _tiku_point_counts([point.name for point in points])

    def build_row(point) -> dict:
        bank = question_bank.bank_of(point.name)
        local_count = int(bank.get("size") or 0)
        cached_items = cached_bank(goal.id, point.name, 60)
        online_count = len(cached_items)
        external_cached = sum(
            1 for item in cached_items if item.get("source") == question_bank.SOURCE_EXTERNAL
        )
        tiku_cached = sum(
            1 for item in cached_items if item.get("source") == tiku_bank.SOURCE_TIKU
        )
        tiku_count = tiku_counts.get(point.name, 0)
        # 出题优先级：自建题库 → 在线缓存 → 外部题库 API → 模型 → 内置题库 → 规则题。
        # 计数按「实际会发生什么」独立统计，避免有内置题时把在线缓存一律算成内置题库。
        if tiku_cached:
            source = "tiku"
        elif external_cached:
            source = "external_cache"
        elif online_count > external_cached:
            source = "online_cache"
        elif tiku_count:
            source = "tiku"
        elif settings.QUESTION_BANK_API_URL:
            source = "external_api"
        elif llm.available:
            source = "model"
        elif local_count:
            source = "local"
        else:
            source = "rule"
        return {
            "kp_id": point.id,
            "kp_name": point.name,
            "is_parent": point.id not in leaves_ids,
            "module": bank.get("module")
            or next(
                (item.name for item in points if item.id == point.parent_id),
                "自定义知识点",
            ),
            "bank_key": bank.get("key"),
            "local_question_count": local_count,
            "cached_question_count": online_count,
            "tiku_question_count": tiku_count,
            "material": quiz_material.material_kind([point.name], goal.exam_name) or "",
            "language": bank.get("language"),
            "source": source,
        }

    leaves_ids = {point.id for point in leaves}
    all_items = [build_row(point) for point in points]
    row_of = {row["kp_id"]: row for row in all_items}

    point_items = []
    counts = {
        "tiku": 0,
        "local": 0,
        "online_cache": 0,
        "external_cache": 0,
        "external_api": 0,
        "model": 0,
        "rule": 0,
    }
    local_cover = 0  # 有内置题库可兜底的知识点数（与「实际来源」独立）
    tiku_cover = 0
    for point in leaves:
        row = row_of[point.id]
        counts[row["source"]] += 1
        if row["local_question_count"]:
            local_cover += 1
        if row["tiku_question_count"]:
            tiku_cover += 1
        point_items.append(row)

    banks = [
        {
            "key": bank["key"],
            "module": bank.get("module", ""),
            "language": bank.get("language", "zh"),
            "points": list(bank.get("points") or []),
            "question_count": len(bank.get("items") or []),
        }
        for bank in question_bank.banks()
    ]
    total = len(leaves)
    return {
        "goal_id": goal.id,
        "external_api_configured": bool(settings.QUESTION_BANK_API_URL),
        "online_generation_available": bool(llm.available),
        "tiku_adapter": {
            "configured": tiku_bank.configured(),
            "base_url": settings.TIKU_ADAPTER_URL,
        },
        "summary": {
            "point_count": total,
            "tiku_count": tiku_cover,
            "local_count": local_cover,
            "cached_count": counts["online_cache"],
            "external_cached_count": counts["external_cache"],
            "external_api_count": counts["external_api"],
            "model_count": counts["model"],
            "rule_count": counts["rule"],
            "local_coverage_rate": round(local_cover / total, 3) if total else 0.0,
            "tiku_coverage_rate": round(tiku_cover / total, 3) if total else 0.0,
        },
        "banks": banks,
        "points": point_items,
        # 含父级模块（阅读 / 听力 / 高等数学…）：考点下拉里这些也能被选中，
        # 需要同样的题源信息，否则父级考点没有题量提示
        "all_points": all_items,
    }


async def _tiku_point_counts(names) -> dict:
    """批量取每个知识点在题库里的题量（按 60s 缓存，避免每次打开页面都打 40 次接口）。"""
    if not tiku_bank.configured():
        return {}
    key = "qbank:tiku_counts:" + hashlib.md5("|".join(sorted(names)).encode("utf-8")).hexdigest()
    try:
        cached = cache.get_json(key)
    except Exception:  # noqa: BLE001
        cached = None
    if isinstance(cached, dict):
        return cached
    try:
        report = await tiku_bank.coverage(list(names))
    except Exception:  # noqa: BLE001
        return {}
    counts = {
        name: int((info or {}).get("count") or 0)
        for name, info in (report.get("points") or {}).items()
    }
    try:
        cache.set_json(key, counts, ttl=60)
    except Exception:  # noqa: BLE001
        pass
    return counts


@router.post("/goals/{goal_id}/question-banks/test")
async def test_question_bank(
    goal_id: int,
    kp_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """探测题库是否可用：优先检测 GitHub 自建题库 tikuAdapter，再尝试外部题库 API。不把密钥或地址返回给客户端。"""
    goal = get_user_goal(goal_id, user, db)
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
    ).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids] or points
    selected_point = next((item for item in points if item.id == kp_id), None) if kp_id else None
    if kp_id and selected_point is None:
        raise HTTPException(status_code=404, detail="该知识点不存在或不是当前目标的知识点")
    point = selected_point
    if point and point.id in parent_ids:
        point = next((item for item in leaves if item.parent_id == point.id), None)
        if point is None:
            raise HTTPException(status_code=400, detail="该模块没有可探测的子知识点")
    if point is None and leaves:
        point = leaves[0]
    if point is None:
        return {
            "status": "no_knowledge_points",
            "latency_ms": None,
            "question_count": 0,
            "source": None,
            "detail": "当前目标没有可用于探测的知识点，请先导入资料或应用学科包。",
        }

    if tiku_bank.configured():
        started = time.perf_counter()
        try:
            health = await tiku_bank.get_client().health()
            latency = round((time.perf_counter() - started) * 1000)
            if health.get("status") != "ok":
                return {
                    "status": health.get("status") or "error",
                    "latency_ms": latency,
                    "question_count": 0,
                    "source": "tiku",
                    "kp_name": point.name,
                    "detail": health.get("detail") or "题库服务未就绪，请确认 tikuAdapter 已启动。",
                }
            items = await tiku_bank.pick(point.name, 2)
            courses = health.get("courses")
            course_hint = f"共 {courses} 门课程。" if courses is not None else ""
            if items:
                detail = (
                    f"题库（tikuAdapter）可用。{course_hint}"
                    f"知识点「{point.name}」成功取到 {len(items)} 道题。"
                )
            else:
                detail = (
                    f"题库（tikuAdapter）服务正常。{course_hint}"
                    f"知识点「{point.name}」暂无对应题目，出题时将回退模型或内置题库。"
                )
            return {
                "status": "ok",
                "latency_ms": latency,
                "question_count": len(items),
                "source": "tiku",
                "kp_name": point.name,
                "detail": detail,
            }
        except Exception as exc:  # noqa: BLE001
            latency = round((time.perf_counter() - started) * 1000)
            return {
                "status": "error",
                "latency_ms": latency,
                "question_count": 0,
                "source": "tiku",
                "kp_name": point.name,
                "detail": f"题库探测失败：{exc}",
            }

    if not settings.QUESTION_BANK_API_URL:
        return {
            "status": "not_configured",
            "latency_ms": None,
            "question_count": 0,
            "source": None,
            "kp_name": point.name,
            "detail": "尚未配置题库（tikuAdapter）或外部题库 API。",
        }
    items, result = await fetch_external_bank(goal, point, limit=2)
    if items:
        store_bank(goal.id, point.name, items)
    return {
        **result,
        "question_count": len(items),
        "source": "external",
        "kp_name": point.name,
    }


@router.get("/goals/{goal_id}/question-banks/balance")
async def question_bank_balance(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """查询第三方查题题库剩余点数；不下发 Token。"""
    get_user_goal(goal_id, user, db)
    from ..services.qbank_provider import create_qbank_adapter

    adapter = create_qbank_adapter()
    try:
        return await adapter.check_balance()
    finally:
        await adapter.close()


@router.get("/goals/{goal_id}/flashcards", response_model=FlashcardDeckOut)
def flashcards(
    goal_id: int,
    limit: int = Query(default=20, ge=1, le=60),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlashcardDeckOut:
    goal = get_user_goal(goal_id, user, db)
    return FlashcardDeckOut(**build_deck(db, user.id, goal.id, limit=limit))


@router.get("/goals/{goal_id}/flashcards/{kp_id}/explain", response_model=FlashcardExplainOut)
async def explain_flashcard(
    goal_id: int,
    kp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlashcardExplainOut:
    goal = get_user_goal(goal_id, user, db)
    point = db.get(KnowledgePoint, kp_id)
    if not point or point.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="知识点不存在")
    parent = db.get(KnowledgePoint, point.parent_id) if point.parent_id else None
    record = db.scalar(
        select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id)
    )
    mastery = record.value if record else 0.0
    data = await ai_flashcard_explanation(point, parent.name if parent else None, mastery)
    return FlashcardExplainOut(kp_id=point.id, **data)


@router.post("/goals/{goal_id}/flashcards/{kp_id}/review", response_model=FlashcardReviewOut)
def review_flashcard(
    goal_id: int,
    kp_id: int,
    payload: FlashcardReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlashcardReviewOut:
    goal = get_user_goal(goal_id, user, db)
    try:
        return FlashcardReviewOut(
            **review_card(db, user.id, goal.id, kp_id, payload.remembered)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/goals/{goal_id}/quiz/generate", response_model=QuizGenerateOut)
async def create_quiz(
    goal_id: int,
    payload: QuizGenerateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuizGenerateOut:
    goal = get_user_goal(goal_id, user, db)
    try:
        result = await generate_quiz(db, user, goal, payload.kp_id, payload.count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return QuizGenerateOut(**result)


@router.get("/goals/{goal_id}/quiz/history")
def quiz_history(
    goal_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    filters = (
        QuizAttempt.user_id == user.id,
        QuizAttempt.goal_id == goal.id,
    )
    rows = db.scalars(
        select(QuizAttempt)
        .where(*filters)
        .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
        .limit(limit)
    ).all()
    stats = db.execute(
        select(
            func.count(QuizAttempt.id),
            func.coalesce(func.sum(QuizAttempt.correct), 0),
            func.coalesce(func.sum(QuizAttempt.total), 0),
            func.coalesce(func.avg(QuizAttempt.score), 0),
            func.coalesce(func.sum(case((QuizAttempt.score >= 80, 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((QuizAttempt.score.between(60, 79), 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((QuizAttempt.score.between(40, 59), 1), else_=0)), 0
            ),
            func.coalesce(func.sum(case((QuizAttempt.score < 40, 1), else_=0)), 0),
        ).where(*filters)
    ).one()
    return {
        "total": int(stats[0]),
        "summary": {
            "correct": int(stats[1]),
            "questions": int(stats[2]),
            "avg_score": round(float(stats[3] or 0)),
            "score_distribution": {
                "excellent": int(stats[4]),
                "good": int(stats[5]),
                "warning": int(stats[6]),
                "fail": int(stats[7]),
            },
        },
        "items": [
            {
                "id": row.id,
                "score": row.score,
                "correct": row.correct,
                "total": row.total,
                "wrong": row.wrong_count,
                "engine": row.engine,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.post("/goals/{goal_id}/quiz/submit", response_model=QuizResultOut)
async def submit_quiz(
    goal_id: int,
    payload: QuizSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuizResultOut:
    goal = get_user_goal(goal_id, user, db)
    try:
        result = grade_quiz(db, user, goal, payload.quiz_id, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await quiz_service.enrich_explanations(result.get("wrong") or [])
    return QuizResultOut(**result)
