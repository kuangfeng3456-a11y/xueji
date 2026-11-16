from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Goal, KnowledgeGap, KnowledgePoint, Task, User
from ..schemas import (
    GapOut,
    KnowledgeGraphOut,
    QuizGenerateOut,
    QuizResultOut,
    QuizSubmitIn,
)
from ..services.knowledge_map import build_graph
from ..services.evidence import record_evidence
from ..services.planner import task_to_dict
from ..services import quiz as quiz_service
from ..services.quiz import generate_quiz, grade_quiz

router = APIRouter(tags=["知识漏洞地图"])


def _gap_out(db: Session, gap: KnowledgeGap) -> GapOut:
    point = db.get(KnowledgePoint, gap.kp_id)
    return GapOut(
        id=gap.id,
        kp_id=gap.kp_id,
        kp_name=point.name if point else "",
        status=gap.status,
        evidence=gap.evidence,
        source=gap.source,
    )


def _get_gap(db: Session, gap_id: int, user: User) -> KnowledgeGap:
    gap = db.get(KnowledgeGap, gap_id)
    if not gap or gap.user_id != user.id:
        raise HTTPException(status_code=404, detail="漏洞记录不存在")
    return gap


@router.get("/goals/{goal_id}/knowledge-graph", response_model=KnowledgeGraphOut)
def knowledge_graph(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeGraphOut:
    goal = get_user_goal(goal_id, user, db)
    return KnowledgeGraphOut(**build_graph(db, user, goal))


@router.post("/gaps/{gap_id}/verify", response_model=QuizGenerateOut)
async def verify_gap(
    gap_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuizGenerateOut:
    gap = _get_gap(db, gap_id, user)
    goal = get_user_goal(gap.goal_id, user, db)
    try:
        return QuizGenerateOut(**await generate_quiz(db, user, goal, gap.kp_id, 2))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/gaps/{gap_id}/submit")
async def submit_gap(
    gap_id: int,
    payload: QuizSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    gap = _get_gap(db, gap_id, user)
    goal = get_user_goal(gap.goal_id, user, db)
    try:
        result = grade_quiz(db, user, goal, payload.quiz_id, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await quiz_service.enrich_explanations(result.get("wrong") or [])

    if result["correct"] == result["total"]:
        gap.status = "fixed"
        gap.evidence = "验证题全部通过，已排除该漏洞"
    else:
        gap.status = "verified"
        gap.evidence = f"验证题答错 {len(result['wrong'])} 道，确认存在漏洞"
    gap.verified_at = datetime.utcnow()
    db.commit()

    repair_task_id = None
    if gap.status == "verified":
        point = db.get(KnowledgePoint, gap.kp_id)
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=gap.kp_id,
            day=date.today(),
            title=f"漏洞修复：{point.name if point else '知识点'}",
            type="remedial",
            duration_min=20,
            status="pending",
            reason="验证题确认存在知识漏洞，系统自动插入修复任务并重排。",
            priority=3.6,
            source="gap",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        repair_task_id = task.id

    record_evidence(
        db,
        user.id,
        goal.id,
        "gap_verify",
        gap.kp_name if hasattr(gap, "kp_name") else f"漏洞 {gap.id}",
        {
            "gap_id": gap.id,
            "status": gap.status,
            "evidence": gap.evidence,
            "score": result["score"],
            "wrong": len(result["wrong"]),
        },
        gap.evidence,
        engine=result.get("engine", "rule"),
        commit=True,
    )

    return {
        "gap": _gap_out(db, gap).model_dump(mode="json"),
        "result": result,
        "repair_task_id": repair_task_id,
    }