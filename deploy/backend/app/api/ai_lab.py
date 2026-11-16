import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import (
    FreshnessReport,
    KnowledgePoint,
    Material,
    Mistake,
    PanelReview,
    ProbeItem,
    User,
)
from ..schemas import (
    AgentRunOut,
    DebateOut,
    FreshnessItemOut,
    FreshnessOut,
    PanelOpinionOut,
    PanelReviewIn,
    PanelReviewOut,
    ProbeGenerateIn,
    ProbeOut,
    ProbeSubmitIn,
    ProbeSubmitOut,
    ThoughtTraceOut,
)
from ..services.freshness import scan_freshness
from ..services.panel import list_agent_runs, run_debate, run_review
from ..services.probes import generate_probes, probe_to_dict, submit_probe
from ..services.thought_trace import get_or_create_trace, trace_to_dict

router = APIRouter(tags=["AI 探针与评审"])


def _kp_map(db: Session, goal_id: int) -> dict:
    return {
        point.id: point
        for point in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    }


@router.get("/goals/{goal_id}/probes", response_model=List[ProbeOut])
def list_probes(
    goal_id: int,
    kind: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=60),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[ProbeOut]:
    goal = get_user_goal(goal_id, user, db)
    query = select(ProbeItem).where(ProbeItem.user_id == user.id, ProbeItem.goal_id == goal.id)
    if kind:
        query = query.where(ProbeItem.kind == kind)
    if status:
        query = query.where(ProbeItem.status == status)
    rows = db.scalars(query.order_by(ProbeItem.created_at.desc()).limit(limit)).all()
    point_map = _kp_map(db, goal.id)
    return [ProbeOut(**probe_to_dict(row, point_map)) for row in rows]


@router.post("/goals/{goal_id}/probes/generate", response_model=List[ProbeOut])
async def create_probes(
    goal_id: int,
    payload: ProbeGenerateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[ProbeOut]:
    goal = get_user_goal(goal_id, user, db)
    try:
        items = await generate_probes(
            db, user, goal, kind=payload.kind, count=payload.count, kp_id=payload.kp_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    point_map = _kp_map(db, goal.id)
    return [ProbeOut(**probe_to_dict(item, point_map)) for item in items]


@router.post("/probes/{probe_id}/submit", response_model=ProbeSubmitOut)
def answer_probe(
    probe_id: int,
    payload: ProbeSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProbeSubmitOut:
    probe = db.get(ProbeItem, probe_id)
    if not probe or probe.user_id != user.id:
        raise HTTPException(status_code=404, detail="探针题不存在")
    goal = get_user_goal(probe.goal_id, user, db)
    try:
        result = submit_probe(db, user, goal, probe, payload.chosen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ProbeSubmitOut(**result)


@router.post("/mistakes/{mistake_id}/trace", response_model=ThoughtTraceOut)
async def create_trace(
    mistake_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThoughtTraceOut:
    mistake = db.get(Mistake, mistake_id)
    if not mistake or mistake.user_id != user.id:
        raise HTTPException(status_code=404, detail="错题不存在")
    goal = get_user_goal(mistake.goal_id, user, db)
    trace = await get_or_create_trace(db, user, goal, mistake)
    return ThoughtTraceOut(**trace_to_dict(trace))


@router.get("/mistakes/{mistake_id}/trace", response_model=ThoughtTraceOut)
def read_trace(
    mistake_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThoughtTraceOut:
    mistake = db.get(Mistake, mistake_id)
    if not mistake or mistake.user_id != user.id:
        raise HTTPException(status_code=404, detail="错题不存在")
    from ..models import ThoughtTrace

    trace = db.scalar(select(ThoughtTrace).where(ThoughtTrace.mistake_id == mistake_id))
    if not trace:
        raise HTTPException(status_code=404, detail="尚未生成思维路径回放")
    return ThoughtTraceOut(**trace_to_dict(trace))


@router.post("/goals/{goal_id}/panel/review", response_model=PanelReviewOut)
async def panel_review(
    goal_id: int,
    payload: PanelReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PanelReviewOut:
    goal = get_user_goal(goal_id, user, db)
    result = await run_review(db, user, goal, payload.topic)
    return PanelReviewOut(**result)


@router.get("/goals/{goal_id}/panel/reviews", response_model=List[PanelReviewOut])
def panel_reviews(
    goal_id: int,
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[PanelReviewOut]:
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(PanelReview)
        .where(PanelReview.user_id == user.id, PanelReview.goal_id == goal.id)
        .order_by(PanelReview.created_at.desc())
        .limit(limit)
    ).all()
    result = []
    for row in rows:
        try:
            opinions = json.loads(row.opinions)
        except Exception:
            opinions = []
        try:
            votes = json.loads(row.votes)
        except Exception:
            votes = []
        result.append(
            PanelReviewOut(
                id=row.id,
                topic=row.topic,
                opinions=[PanelOpinionOut(**item) for item in opinions],
                verdict=row.verdict,
                votes=votes,
                engine=row.engine,
                created_at=row.created_at,
            )
        )
    return result


@router.post("/goals/{goal_id}/freshness/scan", response_model=FreshnessOut)
async def scan_materials(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FreshnessOut:
    goal = get_user_goal(goal_id, user, db)
    return FreshnessOut(**await scan_freshness(db, user, goal))


@router.get("/goals/{goal_id}/freshness", response_model=FreshnessOut)
def freshness(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FreshnessOut:
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(FreshnessReport).where(
            FreshnessReport.user_id == user.id, FreshnessReport.goal_id == goal.id
        )
    ).all()
    material_map = {
        material.id: material
        for material in db.scalars(
            select(Material).where(Material.user_id == user.id, Material.goal_id == goal.id)
        ).all()
    }
    items = []
    for row in rows:
        try:
            issues = json.loads(row.issues)
        except Exception:
            issues = []
        material = material_map.get(row.material_id)
        items.append(
            FreshnessItemOut(
                material_id=row.material_id,
                filename=material.filename if material else f"资料 {row.material_id}",
                score=row.score,
                level="fresh" if row.score >= 80 else "warning" if row.score >= 60 else "stale",
                issues=issues,
                suggestion=row.suggestion,
                engine=row.engine,
            )
        )
    overall = round(sum(item.score for item in items) / len(items)) if items else 0
    return FreshnessOut(items=items, overall=overall, scanned_at=rows[0].checked_at if rows else None)

@router.get("/goals/{goal_id}/freshness/history")
async def freshness_history(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(FreshnessReport)
        .where(FreshnessReport.user_id == user.id, FreshnessReport.goal_id == goal.id)
        .order_by(FreshnessReport.checked_at.desc())
        .limit(20)
    ).all()
    material_map = {
        material.id: material
        for material in db.scalars(
            select(Material).where(Material.user_id == user.id, Material.goal_id == goal.id)
        ).all()
    }
    history = []
    for row in rows:
        try:
            issues = json.loads(row.issues)
        except Exception:
            issues = []
        material = material_map.get(row.material_id)
        history.append(
            {
                "material_id": row.material_id,
                "filename": material.filename if material else f"资料 {row.material_id}",
                "score": row.score,
                "level": "fresh" if row.score >= 80 else "warning" if row.score >= 60 else "stale",
                "issues": issues,
                "suggestion": row.suggestion,
                "engine": row.engine,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            }
        )
    return {"history": history, "total": len(history)}

@router.post("/goals/{goal_id}/panel/debate", response_model=DebateOut)
async def panel_debate(
    goal_id: int,
    payload: PanelReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DebateOut:
    goal = get_user_goal(goal_id, user, db)
    result = await run_debate(db, user, goal, payload.topic)
    return DebateOut(**result)


@router.get("/goals/{goal_id}/panel/runs", response_model=List[AgentRunOut])
def panel_agent_runs(
    goal_id: int,
    run_id: Optional[str] = None,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[AgentRunOut]:
    goal = get_user_goal(goal_id, user, db)
    return [AgentRunOut(**item) for item in list_agent_runs(db, user, goal, run_id=run_id, limit=limit)]