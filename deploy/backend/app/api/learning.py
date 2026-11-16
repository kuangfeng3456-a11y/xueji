import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..agents.diagnoser import diagnose
from ..agents.reporter_agent import reporter_generate
from ..cache import cache
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Goal, KnowledgePoint, Mastery, Mistake, Report, User
from ..schemas import (
    MasteryOut,
    MistakeCreate,
    MistakeOut,
    PhotoUploadOut,
    ReplanResult,
    ReportOut,
    TaskOut,
)
from ..services.doc_export import build_mistakes_docx, build_report_docx, build_report_pdf
from ..services.mastery_service import apply_answer, ensure_mastery, record_history
from ..services.planner import replan, task_to_dict


router = APIRouter(prefix="/goals", tags=["错题、掌握度与周报"])


class AnswerIn(BaseModel):
    correct: bool


def _kp_map(db: Session, goal_id: int) -> dict:
    return {
        point.id: point
        for point in db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    }


def _mistake_out(mistake: Mistake, kp_map: dict) -> MistakeOut:
    point = kp_map.get(mistake.kp_id) if mistake.kp_id else None
    return MistakeOut(
        id=mistake.id,
        question=mistake.question,
        user_answer=mistake.user_answer,
        correct_answer=mistake.correct_answer,
        category=mistake.category,
        category_label=mistake.category_label,
        suggestion=mistake.suggestion,
        source=mistake.source,
        image_url=mistake.image_url,
        created_at=mistake.created_at,
        kp_id=mistake.kp_id,
        kp_name=point.name if point else None,
    )


@router.post("/{goal_id}/mistakes/photo", response_model=PhotoUploadOut, status_code=201)
async def upload_mistake_photo(
    goal_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PhotoUploadOut:
    get_user_goal(goal_id, user, db)
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="图片超过 5MB，请压缩后再上传")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="仅支持 jpg / jpeg / png / webp 图片")
    folder = Path(settings.UPLOAD_DIR) / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (folder / filename).write_bytes(data)
    return PhotoUploadOut(url=f"/uploads/{user.id}/{filename}", filename=filename)


@router.post("/{goal_id}/mistakes", status_code=201)
async def create_mistake(
    goal_id: int,
    payload: MistakeCreate,
    auto_replan: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)

    count = cache.incr(f"ratelimit:diagnose:{user.id}", ttl=60)
    if count > 30:
        raise HTTPException(status_code=429, detail="错题诊断过于频繁，请稍后再试")

    kp_map = _kp_map(db, goal.id)
    point = kp_map.get(payload.kp_id) if payload.kp_id else None
    if payload.kp_id and not point:
        raise HTTPException(status_code=400, detail="关联知识点不存在")

    category, label, suggestion, engine = await diagnose(
        payload.question, payload.user_answer, payload.correct_answer, point.name if point else None
    )

    mistake = Mistake(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=point.id if point else None,
        question=payload.question,
        user_answer=payload.user_answer,
        correct_answer=payload.correct_answer,
        category=category,
        category_label=label,
        suggestion=suggestion,
        source=payload.source,
        image_url=payload.image_url,
    )
    db.add(mistake)
    db.flush()

    mastery_value = None
    if point:
        record = apply_answer(db, user.id, point, correct=False)
        mastery_value = record.value

    db.commit()
    db.refresh(mistake)
    cache.delete(f"dashboard:{user.id}:{goal.id}")

    result = {
        "mistake": _mistake_out(mistake, kp_map).model_dump(mode="json"),
        "diagnosis": {
            "category": category,
            "category_label": label,
            "suggestion": suggestion,
            "engine": engine,
            "mastery": mastery_value,
        },
        "replan": None,
    }

    if auto_replan:
        replan_result = replan(db, user.id, goal, trigger="mistake")
        result["replan"] = {
            "trigger": replan_result["trigger"],
            "changes": replan_result["changes"],
            "tasks": [TaskOut(**task).model_dump(mode="json") for task in replan_result["tasks"]],
        }
    return result


@router.get("/{goal_id}/mistakes", response_model=List[MistakeOut])
def list_mistakes(
    goal_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[MistakeOut]:
    goal = get_user_goal(goal_id, user, db)
    query = select(Mistake).where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
    if category:
        query = query.where(Mistake.category == category)
    rows = db.scalars(query.order_by(Mistake.created_at.desc()).limit(limit)).all()
    kp_map = _kp_map(db, goal.id)
    return [_mistake_out(row, kp_map) for row in rows]


@router.get("/{goal_id}/mistakes/summary")
def mistake_summary(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """错题与掌握度的全量统计。

    列表接口默认只返回最近 20 条，前端不能拿当页数据当总数，
    因此把聚合下推到 SQL，保证「错因分布 / 总数 / 薄弱点数」都是全量口径。
    """
    goal = get_user_goal(goal_id, user, db)

    cat_rows = db.execute(
        select(Mistake.category, func.count())
        .where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
        .group_by(Mistake.category)
    ).all()
    by_category: Dict[str, int] = {"concept": 0, "method": 0, "careless": 0, "time": 0}
    total = 0
    for category, count in cat_rows:
        total += int(count)
        if category in by_category:
            by_category[category] = int(count)
        else:
            by_category[str(category or "unknown")] = int(count)

    since = datetime.combine(date.today() - timedelta(days=6), datetime.min.time())
    recent = db.scalar(
        select(func.count())
        .select_from(Mistake)
        .where(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.created_at >= since,
        )
    )

    mastery_agg = db.execute(
        select(
            func.count(),
            func.avg(Mastery.value),
            func.sum(case((Mastery.value < 0.5, 1), else_=0)),
        )
        .select_from(Mastery)
        .join(KnowledgePoint, KnowledgePoint.id == Mastery.kp_id)
        .where(Mastery.user_id == user.id, KnowledgePoint.goal_id == goal.id)
    ).one()
    point_total, avg_value, weak = mastery_agg
    point_total = int(point_total or 0)

    return {
        "total": total,
        "by_category": by_category,
        "last_7_days": int(recent or 0),
        "avg_mastery": round(float(avg_value), 4) if avg_value is not None else None,
        "weak_points": int(weak or 0),
        "point_total": point_total,
    }


@router.delete("/mistakes/{mistake_id}", status_code=204)
def delete_mistake(
    mistake_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    mistake = db.get(Mistake, mistake_id)
    if not mistake or mistake.user_id != user.id:
        raise HTTPException(status_code=404, detail="错题不存在")
    db.delete(mistake)
    db.commit()


@router.post("/{goal_id}/mastery/{kp_id}/answer")
def answer_knowledge_point(
    goal_id: int,
    kp_id: int,
    payload: AnswerIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    goal = get_user_goal(goal_id, user, db)
    point = db.get(KnowledgePoint, kp_id)
    if not point or point.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="知识点不存在")
    record = apply_answer(db, user.id, point, correct=payload.correct)
    db.commit()
    cache.delete(f"dashboard:{user.id}:{goal.id}")
    return {
        "kp_id": point.id,
        "kp_name": point.name,
        "value": record.value,
        "next_review_at": record.next_review_at,
        "review_stage": record.review_stage,
    }


@router.get("/{goal_id}/mastery", response_model=List[MasteryOut])
def list_mastery(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[MasteryOut]:
    goal = get_user_goal(goal_id, user, db)
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    records = {
        row.kp_id: row
        for row in db.scalars(
            select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id.in_([p.id for p in points] or [0]))
        ).all()
    }
    week_ago = date.today() - timedelta(days=7)
    from ..models import MasteryHistory

    history_rows = db.scalars(
        select(MasteryHistory).where(
            MasteryHistory.user_id == user.id,
            MasteryHistory.kp_id.in_([p.id for p in points] or [0]),
            MasteryHistory.day <= week_ago,
        )
    ).all()
    baseline_map = {}
    for row in history_rows:
        current = baseline_map.get(row.kp_id)
        if current is None or row.day > current.day:
            baseline_map[row.kp_id] = row

    result = []
    for point in sorted(points, key=lambda p: p.weight, reverse=True):
        record = records.get(point.id)
        value = record.value if record else 0.0
        baseline = baseline_map.get(point.id)
        result.append(
            MasteryOut(
                kp_id=point.id,
                kp_name=point.name,
                value=value,
                next_review_at=record.next_review_at if record else None,
                delta_7d=round(value - (baseline.value if baseline else value), 3),
            )
        )
    return result


@router.post("/{goal_id}/reports", response_model=ReportOut)
async def create_report(
    goal_id: int,
    week_start: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    goal = get_user_goal(goal_id, user, db)
    report = await reporter_generate(db, user, goal, week_start=week_start)
    cache.delete(f"dashboard:{user.id}:{goal.id}")
    return ReportOut.model_validate(report)


@router.get("/{goal_id}/reports", response_model=List[ReportOut])
def list_reports(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[ReportOut]:
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(Report)
        .where(Report.user_id == user.id, Report.goal_id == goal.id)
        .order_by(Report.week_start.desc())
    ).all()
    return [ReportOut.model_validate(row) for row in rows]


@router.get("/{goal_id}/reports/latest/export")
def export_latest_report(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> JSONResponse:
    """导出最新周报（文档 9.4 / E3）：带 AI 内容标识与内容编号。"""
    goal = get_user_goal(goal_id, user, db)
    row = db.scalar(
        select(Report)
        .where(Report.user_id == user.id, Report.goal_id == goal.id)
        .order_by(Report.week_start.desc())
    )
    if not row:
        raise HTTPException(status_code=404, detail="还没有周报，请先生成")
    content_id = f"xueji-report-{uuid.uuid4().hex[:12]}"
    payload = {
        "report": {
            "id": row.id,
            "goal_id": row.goal_id,
            "week_start": row.week_start,
            "week_end": row.week_end,
            "completion_rate": row.completion_rate,
            "mastery_delta": row.mastery_delta,
            "focus": row.focus,
            "content": row.content,
            "ai_assisted": True,
        },
        "ai_disclosure": {
            "generated": True,
            "contains_ai_generated_content": True,
            "service_provider": "学迹 · 自适应 AI 学习教练",
            "provider_code": "xueji",
            "content_id": content_id,
            "label": "AI 辅助生成",
            "note": "本文件包含 AI 辅助生成的周报内容，仅供参考，不构成承诺或诊断。",
        },
    }
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={
            "Content-Disposition": f'attachment; filename="xueji-report-{row.week_start}.json"',
            "X-AI-Generated": "true",
            "X-AI-Provider": "xueji",
            "X-AI-Content-Id": content_id,
            "X-Content-Disclosure": "AI-assisted",
        },
    )


def _latest_report_row(db: Session, user: User, goal_id: int):
    goal = get_user_goal(goal_id, user, db)
    row = db.scalar(
        select(Report)
        .where(Report.user_id == user.id, Report.goal_id == goal.id)
        .order_by(Report.week_start.desc())
    )
    if not row:
        raise HTTPException(status_code=404, detail="还没有周报，请先生成")
    return goal, row


def _report_payload(row: Report) -> Dict:
    return {
        "week_start": row.week_start.isoformat(),
        "week_end": row.week_end.isoformat(),
        "completion_rate": row.completion_rate,
        "mastery_delta": row.mastery_delta,
        "focus": row.focus,
        "content": row.content,
    }


@router.get("/{goal_id}/reports/latest/export.docx")
def export_report_docx(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    goal, row = _latest_report_row(db, user, goal_id)
    content_id = f"xueji-report-{uuid.uuid4().hex[:12]}"
    data = build_report_docx(_report_payload(row), goal.exam_name, content_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="xueji-report-{row.week_start}.docx"',
            "X-AI-Generated": "true",
            "X-AI-Content-Id": content_id,
            "X-Content-Disclosure": "AI-assisted",
        },
    )


@router.get("/{goal_id}/reports/latest/export.pdf")
def export_report_pdf(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    goal, row = _latest_report_row(db, user, goal_id)
    content_id = f"xueji-report-{uuid.uuid4().hex[:12]}"
    data = build_report_pdf(_report_payload(row), goal.exam_name, content_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="xueji-report-{row.week_start}.pdf"',
            "X-AI-Generated": "true",
            "X-AI-Content-Id": content_id,
            "X-Content-Disclosure": "AI-assisted",
        },
    )


@router.get("/{goal_id}/mistakes/export.docx")
def export_mistakes_docx(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(Mistake)
        .where(Mistake.user_id == user.id, Mistake.goal_id == goal.id)
        .order_by(Mistake.created_at.desc())
    ).all()
    kp_map = _kp_map(db, goal.id)
    items = []
    for row in rows:
        out = _mistake_out(row, kp_map)
        items.append(out.model_dump() if hasattr(out, "model_dump") else dict(out))
    content_id = f"xueji-mistakes-{uuid.uuid4().hex[:12]}"
    data = build_mistakes_docx(items, goal.exam_name, content_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="xueji-mistakes-{date.today()}.docx"',
            "X-AI-Generated": "true",
            "X-AI-Content-Id": content_id,
            "X-Content-Disclosure": "AI-assisted",
        },
    )


@router.get("/{goal_id}/reports/latest", response_model=Optional[ReportOut])
def latest_report(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Optional[ReportOut]:
    goal = get_user_goal(goal_id, user, db)
    row = db.scalar(
        select(Report)
        .where(Report.user_id == user.id, Report.goal_id == goal.id)
        .order_by(Report.week_start.desc())
    )
    return ReportOut.model_validate(row) if row else None