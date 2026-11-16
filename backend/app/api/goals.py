from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import Goal, KnowledgePoint, Mastery, Material, QuizAttempt, Task, User
from ..schemas import (
    GoalCreate,
    GoalOut,
    KnowledgePointCreate,
    KnowledgePointOut,
    MaterialOut,
    MaterialTextIn,
)
from ..services.mastery_service import ensure_mastery
from ..services.knowledge import persist_points
from ..services.materials import extract_knowledge_points, extract_text
from ..services.rag import index_material
from ..services.safety_events import record_safety_event
from ..services.validator import scan_text
from ..services.rules import days_left

router = APIRouter(prefix="/goals", tags=["目标与资料"])


def build_goal_out(db: Session, user_id: int, goal: Goal) -> GoalOut:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    point_ids = [point.id for point in points]
    mastery_rows = (
        db.scalars(
            select(Mastery).where(Mastery.user_id == user_id, Mastery.kp_id.in_(point_ids))
        ).all()
        if point_ids
        else []
    )
    avg_mastery = round(sum(row.value for row in mastery_rows) / len(mastery_rows), 3) if mastery_rows else 0.0
    tasks = db.scalars(select(Task).where(Task.user_id == user_id, Task.goal_id == goal.id)).all()
    done = sum(1 for task in tasks if task.status == "done")
    rate = round(done / len(tasks), 3) if tasks else 0.0
    return GoalOut(
        id=goal.id,
        exam_name=goal.exam_name,
        exam_date=goal.exam_date,
        daily_minutes=goal.daily_minutes,
        force_mode=bool(goal.force_mode),
        min_daily_minutes=goal.min_daily_minutes,
        camera_required=bool(goal.camera_required),
        created_at=goal.created_at,
        days_left=days_left(goal.exam_date),
        knowledge_count=len(points),
        avg_mastery=avg_mastery,
        completed_rate=rate,
    )


@router.get("", response_model=List[GoalOut])
def list_goals(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[GoalOut]:
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc())).all()
    return [build_goal_out(db, user.id, goal) for goal in goals]


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> GoalOut:
    goal = get_user_goal(goal_id, user, db)
    return build_goal_out(db, user.id, goal)


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(
    payload: GoalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GoalOut:
    goal = Goal(
        user_id=user.id,
        exam_name=payload.exam_name,
        exam_date=payload.exam_date,
        daily_minutes=payload.daily_minutes,
        force_mode=payload.force_mode,
        min_daily_minutes=payload.min_daily_minutes,
        camera_required=payload.camera_required,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return build_goal_out(db, user.id, goal)


@router.put("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int,
    payload: GoalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GoalOut:
    goal = get_user_goal(goal_id, user, db)
    goal.exam_name = payload.exam_name
    goal.exam_date = payload.exam_date
    goal.daily_minutes = payload.daily_minutes
    goal.force_mode = payload.force_mode
    goal.min_daily_minutes = payload.min_daily_minutes
    goal.camera_required = payload.camera_required
    db.commit()
    db.refresh(goal)
    return build_goal_out(db, user.id, goal)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    goal = get_user_goal(goal_id, user, db)
    db.query(QuizAttempt).filter(
        QuizAttempt.user_id == user.id,
        QuizAttempt.goal_id == goal.id,
    ).delete(synchronize_session=False)
    db.delete(goal)
    db.commit()


@router.get("/{goal_id}/knowledge-points", response_model=List[KnowledgePointOut])
def list_knowledge_points(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[KnowledgePointOut]:
    goal = get_user_goal(goal_id, user, db)
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id).order_by(KnowledgePoint.weight.desc())
    ).all()
    mastery_map = {
        row.kp_id: row
        for row in db.scalars(
            select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id.in_([p.id for p in points] or [0]))
        ).all()
    }
    result = []
    for point in points:
        record = mastery_map.get(point.id)
        result.append(
            KnowledgePointOut(
                id=point.id,
                name=point.name,
                parent_id=point.parent_id,
                weight=point.weight,
                mastery=record.value if record else 0.0,
                next_review_at=record.next_review_at if record else None,
            )
        )
    return result


@router.post("/{goal_id}/knowledge-points", response_model=KnowledgePointOut, status_code=201)
def create_knowledge_point(
    goal_id: int,
    payload: KnowledgePointCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgePointOut:
    goal = get_user_goal(goal_id, user, db)
    exists = db.scalar(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id, KnowledgePoint.name == payload.name)
    )
    if exists:
        raise HTTPException(status_code=400, detail="该知识点已存在")
    if payload.parent_id is not None:
        parent = db.get(KnowledgePoint, payload.parent_id)
        if not parent or parent.goal_id != goal.id:
            raise HTTPException(status_code=400, detail="父知识点不存在")
    point = KnowledgePoint(
        goal_id=goal.id, name=payload.name, parent_id=payload.parent_id, weight=payload.weight
    )
    db.add(point)
    db.commit()
    db.refresh(point)
    record = ensure_mastery(db, user.id, point)
    db.commit()
    return KnowledgePointOut(
        id=point.id,
        name=point.name,
        parent_id=point.parent_id,
        weight=point.weight,
        mastery=record.value,
        next_review_at=record.next_review_at,
    )


@router.delete("/{goal_id}/knowledge-points/{kp_id}", status_code=204)
def delete_knowledge_point(
    goal_id: int,
    kp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    goal = get_user_goal(goal_id, user, db)
    point = db.get(KnowledgePoint, kp_id)
    if not point or point.goal_id != goal.id:
        raise HTTPException(status_code=404, detail="知识点不存在")
    db.query(Mastery).filter(Mastery.user_id == user.id, Mastery.kp_id == kp_id).delete()
    db.query(Task).filter(Task.user_id == user.id, Task.kp_id == kp_id).delete()
    db.delete(point)
    db.commit()


@router.post("/{goal_id}/materials/text", response_model=List[KnowledgePointOut], status_code=201)
async def import_material_text(
    goal_id: int,
    payload: MaterialTextIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[KnowledgePointOut]:
    goal = get_user_goal(goal_id, user, db)
    issues = scan_text(payload.content)
    if issues:
        # 文档 9.3 / 附录 B：注入企图记入 safety_events，不保存资料原文
        record_safety_event(db, user.id, "injection", "high", "material_rejected")
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="资料包含疑似注入指令，已拒绝导入：" + issues[0]["message"],
        )
    points, engine = await extract_knowledge_points(payload.content)
    if not points:
        raise HTTPException(
            status_code=400,
            detail=(
                "未能从资料中抽取到知识点。AI 解析需要联网（请检查网络后重试）；"
                "也可以粘贴带层级的大纲内容（# 一级标题、- 子项），走本地规则解析，无需联网。"
            ),
        )
    material = Material(
        user_id=user.id, goal_id=goal.id, filename=payload.filename, content=payload.content[:20000]
    )
    db.add(material)
    db.flush()
    index_material(db, user.id, goal.id, material)
    created = persist_points(db, user.id, goal, points)
    db.commit()
    return [
        KnowledgePointOut(
            id=item["id"],
            name=item["name"],
            parent_id=item["parent_id"],
            weight=item["weight"],
            mastery=0.0,
        )
        for item in created
    ]


@router.post("/{goal_id}/materials/upload", response_model=List[KnowledgePointOut], status_code=201)
async def import_material_file(
    goal_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[KnowledgePointOut]:
    goal = get_user_goal(goal_id, user, db)
    raw = await file.read()
    try:
        text = extract_text(file.filename or "upload.txt", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    issues = scan_text(text)
    if issues:
        record_safety_event(db, user.id, "injection", "high", "file_rejected")
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="资料包含疑似注入指令，已拒绝导入：" + issues[0]["message"],
        )
    points, _ = await extract_knowledge_points(text)
    if not points:
        raise HTTPException(status_code=400, detail="未能从文件中抽取到知识点")
    db.add(
        Material(user_id=user.id, goal_id=goal.id, filename=file.filename or "upload", content=text[:20000])
    )
    db.flush()
    material = db.query(Material).order_by(Material.id.desc()).first()
    if material:
        index_material(db, user.id, goal.id, material)
    created = persist_points(db, user.id, goal, points)
    db.commit()
    return [
        KnowledgePointOut(
            id=item["id"],
            name=item["name"],
            parent_id=item["parent_id"],
            weight=item["weight"],
            mastery=0.0,
        )
        for item in created
    ]


@router.get("/{goal_id}/materials", response_model=List[MaterialOut])
def list_materials(
    goal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[MaterialOut]:
    goal = get_user_goal(goal_id, user, db)
    rows = db.scalars(
        select(Material)
        .where(Material.user_id == user.id, Material.goal_id == goal.id)
        .order_by(Material.created_at.desc())
    ).all()
    return [MaterialOut.model_validate(row) for row in rows]


@router.post("/{goal_id}/quiz/search-chaoxing")
async def search_chaoxing_questions(
    goal_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从第三方查题题库按题干 + 选项查询答案。

    Request:
        {
            "question": "题干（必填）",
            "options": ["选项 A", "选项 B", "选项 C", "选项 D"],  // 可选
            "question_type": "single_choice|multiple_choice|true_false|...",  // 可选
            "platform": "chaoxing|xuexitong|mooc|..."  // 可选，仅元数据展示
        }

    Response:
        {
            "status": "ok" / "no_answer" / "invalid_token" / ...,
            "metadata": {
                "status": "ok",
                "latency_ms": 123,
                "detail": "命中 1 项答案",
                "answer_texts": ["正确选项文本"],
                "answer_indexes": [0],
                "mode": "cx",
                "platform": "chaoxing"
            }
        }
    """
    goal = get_user_goal(goal_id, user, db)

    question = (payload.get("question") or payload.get("knowledge_point") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="题干不能为空")

    options = payload.get("options")
    question_type = payload.get("question_type", "single_choice").strip()
    platform = payload.get("platform", "chaoxing").strip()

    from ..services.qbank_provider import create_qbank_adapter

    adapter = create_qbank_adapter(platform=platform)
    try:
        metadata = await adapter.lookup(
            question=question,
            question_type=question_type,
            options=options,
        )
        return {"status": metadata.get("status", "ok"), "metadata": metadata}
    finally:
        await adapter.close()
