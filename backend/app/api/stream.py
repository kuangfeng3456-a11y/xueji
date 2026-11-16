"""SSE 流式接口（文档 7.1）：每日教练 P07 逐段返回，校验后才给出最终文案。

约定：
- `stage` 告知前端规则内核进行到哪一步；
- `delta` 是模型的增量文本（仅作生成进度，界面不把它当作最终答案）；
- `result` 是校验通过的统一信封（界面才展示）；
- `fallback` 表示模型不可用或输出未过校验，改用规则文案，并如实说明原因。
"""

import asyncio
import json
from datetime import date
from typing import AsyncIterator, Dict, List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..deps import get_current_user, get_user_goal
from ..llm import llm
from ..models import Goal, KnowledgePoint, Mastery, Task, User
from ..prompts.library import build_messages, check_envelope, parse_json_strict
from ..services import tutor
from ..services.lsv import build_lsv

router = APIRouter(tags=["流式输出"])


class SocraticStreamIn(BaseModel):
    kp_id: int
    message: str = Field(default="", max_length=500)
    level: str = Field(default="direction", max_length=16)


class VoiceStreamIn(BaseModel):
    question: str = Field(default="", max_length=500)


def _sse(event: str, data: Dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _fallback_text(lsv: Dict) -> str:
    goal = lsv.get("goal", {})
    load = lsv.get("load", {})
    readiness = lsv.get("readiness", {})
    days = goal.get("days_left")
    tasks = load.get("today_tasks")
    minutes = load.get("today_planned_min")
    score = readiness.get("score")
    if not days and days != 0:
        return "还没有考试目标，先创建目标再生成今日提醒。"
    return (
        f"距「{goal.get('name', '考试')}」还有 {days} 天，"
        f"今天安排了 {tasks} 个任务、约 {minutes} 分钟，准备度 {score} 分。"
        "先把最高优先级的任务做完，再决定要不要加量。"
    )


@router.get("/goals/{goal_id}/coach/stream")
async def coach_stream(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_user_goal(goal_id, user, db)  # 归属校验在进入流之前完成，越权直接 404

    async def generate() -> AsyncIterator[str]:
        with SessionLocal() as session:
            current_user = session.get(User, user.id)
            goal = get_user_goal(goal_id, current_user, session)

            yield _sse("stage", {"stage": "state", "label": "读取学习状态向量"})
            lsv = await asyncio.to_thread(build_lsv, session, current_user, goal)

            yield _sse("stage", {"stage": "rules", "label": "规则内核计算今日任务"})
            rows = session.scalars(
                select(Task).where(
                    Task.user_id == current_user.id,
                    Task.goal_id == goal.id,
                    Task.day == date.today(),
                )
            ).all()
            tasks: List[Dict] = [
                {
                    "task_id": row.id,
                    "title": row.title,
                    "minutes": row.duration_min,
                    "status": row.status,
                    "type": row.type,
                    "reason": row.reason,
                }
                for row in rows
            ]
            rule_output = {
                "readiness": lsv.get("readiness"),
                "load": lsv.get("load"),
                "risks": lsv.get("risks"),
                "phase": lsv.get("phase"),
            }

            fallback = _fallback_text(lsv)
            if not llm.available:
                yield _sse("fallback", {"text": fallback, "reason": "模型未配置或熔断中，使用规则文案"})
                return

            messages, meta = build_messages(
                "P07",
                learner_state_json=lsv,
                rule_output_json=rule_output,
                today_tasks_json=tasks,
                event_json_or_null=None,
            )
            yield _sse("stage", {"stage": "model", "label": "模型生成教练提醒"})
            stream = await llm.chat_stream(
                messages[0]["content"],
                messages[1]["content"],
                temperature=meta["temperature"] or 0.5,
                max_tokens=meta["max_tokens"] or 800,
                prompt_id=meta["prompt_id"],
                prompt_version=meta["version"],
                prompt_hash=meta["hash"],
                tier=meta["tier"] or "general",
                user_id=current_user.id,
                timeout=meta["timeout_s"],
            )
            if stream is None:
                yield _sse("fallback", {"text": fallback, "reason": "模型调用失败，使用规则文案"})
                return

            chunks: List[str] = []
            async for delta in stream:
                chunks.append(delta)
                yield _sse("delta", {"text": delta})

            raw = "".join(chunks)
            try:
                envelope = parse_json_strict(raw)
                errors = check_envelope(envelope)
            except ValueError as exc:
                envelope, errors = None, [str(exc)]
            if envelope is None or errors:
                yield _sse(
                    "fallback",
                    {"text": fallback, "reason": "模型输出未通过统一信封校验：" + "; ".join(errors[:2])},
                )
                return

            yield _sse(
                "result",
                {
                    "data": envelope.get("data"),
                    "confidence": envelope.get("confidence"),
                    "warnings": envelope.get("warnings"),
                    "prompt": {
                        "id": meta["prompt_id"],
                        "version": meta["version"],
                        "hash": meta["hash"],
                    },
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def _stream_response(generator):
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_prompt_stream(
    prompt_id: str,
    variables: Dict,
    fallback_text: str,
    user_id: int,
) -> AsyncIterator[str]:
    """通用提示词流式：stage → delta → result/fallback（P06/P07/P15 共用）。"""
    messages, meta = build_messages(prompt_id, **variables)
    yield _sse("stage", {"stage": "model", "label": f"模型生成（{prompt_id}）"})
    if not llm.available:
        yield _sse("fallback", {"text": fallback_text, "reason": "模型未配置或熔断中，使用规则文案"})
        return
    stream = await llm.chat_stream(
        messages[0]["content"],
        messages[1]["content"],
        temperature=meta["temperature"] or 0.5,
        max_tokens=meta["max_tokens"] or 900,
        prompt_id=meta["prompt_id"],
        prompt_version=meta["version"],
        prompt_hash=meta["hash"],
        tier=meta["tier"] or "general",
        user_id=user_id,
        timeout=meta["timeout_s"],
    )
    if stream is None:
        yield _sse("fallback", {"text": fallback_text, "reason": "模型调用失败，使用规则文案"})
        return
    chunks: List[str] = []
    async for delta in stream:
        chunks.append(delta)
        yield _sse("delta", {"text": delta})
    raw = "".join(chunks)
    try:
        envelope = parse_json_strict(raw)
        errors = check_envelope(envelope)
    except ValueError as exc:
        envelope, errors = None, [str(exc)]
    if envelope is None or errors:
        yield _sse(
            "fallback",
            {"text": fallback_text, "reason": "模型输出未通过统一信封校验：" + "; ".join(errors[:2])},
        )
        return
    yield _sse(
        "result",
        {
            "data": envelope.get("data"),
            "confidence": envelope.get("confidence"),
            "warnings": envelope.get("warnings"),
            "prompt": {"id": meta["prompt_id"], "version": meta["version"], "hash": meta["hash"]},
        },
    )


@router.post("/goals/{goal_id}/socratic/stream")
async def socratic_stream(
    goal_id: int,
    payload: SocraticStreamIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """P06 苏格拉底讲解的 SSE 版本（文档 7.1：讲解官使用流式）。"""
    goal = get_user_goal(goal_id, user, db)
    point = db.get(KnowledgePoint, payload.kp_id)
    if not point or point.goal_id != goal.id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="知识点不存在")
    beginner = db.scalar(
        select(Mastery).where(Mastery.user_id == user.id, Mastery.kp_id == point.id)
    )
    mastery = beginner.value if beginner else 0.0
    fallback = f"先别急着看答案：关于「{point.name}」，你能说出它的定义和一个例子吗？"

    async def generate() -> AsyncIterator[str]:
        with SessionLocal() as session:
            current_user = session.get(User, user.id)
            variables = {
                "hint_level": payload.level,
                "learner_state_json": {
                    "kp_id": point.id,
                    "kp_name": point.name,
                    "mastery": round(mastery, 3),
                    "weight": point.weight,
                },
                "question_json": {
                    "kp_id": point.id,
                    "name": point.name,
                    "mastery": round(mastery, 3),
                },
                "student_message": payload.message,
            }
            async for chunk in _run_prompt_stream("P06", variables, fallback, current_user.id):
                yield chunk

    return _stream_response(generate())


@router.post("/voice/ask/stream")
async def voice_stream(
    payload: VoiceStreamIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """P15 语音教练的 SSE 版本（文档 7.1：语音教练使用流式）。"""
    fallback = "我没听清，可以再说一次吗？"

    async def generate() -> AsyncIterator[str]:
        with SessionLocal() as session:
            current_user = session.get(User, user.id)
            goal = session.scalar(
                select(Goal)
                .where(Goal.user_id == user.id)
                .order_by(Goal.created_at.desc())
                .limit(1)
            )
            lsv = await asyncio.to_thread(build_lsv, session, current_user, goal) if goal else {}
            tasks = []
            if goal:
                rows = session.scalars(
                    select(Task).where(
                        Task.user_id == current_user.id,
                        Task.goal_id == goal.id,
                        Task.day == date.today(),
                    )
                ).all()
                tasks = [
                    {"task_id": row.id, "title": row.title, "minutes": row.duration_min, "status": row.status}
                    for row in rows
                ]
            variables = {
                "allowed_actions_json": [
                    {"type": "open_plan", "label": "打开学习计划"},
                    {"type": "start_task", "label": "开始今日任务"},
                    {"type": "generate_quiz", "label": "生成随堂测"},
                ],
                "history_json": [],
                "learner_state_json": lsv,
                "rule_output_json": {"tasks_today": tasks, "readiness": lsv.get("readiness")},
                "user_utterance": payload.question,
            }
            async for chunk in _run_prompt_stream("P15", variables, fallback, current_user.id):
                yield chunk
    return _stream_response(generate())
