"""思维路径回放器：把错题拆成思维步骤，指出在哪一步偏离。"""

import json
from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import Goal, Mistake, ThoughtTrace, User
from .evidence import record_evidence


def _fallback(mistake: Mistake) -> Dict:
    category = mistake.category
    if category == "concept":
        steps = [
            {"index": 0, "thought": "读题并定位考点", "verdict": "偏离", "issue": "没有先确认概念定义，直接套用印象"},
            {"index": 1, "thought": "回忆相关定义与边界", "verdict": "缺失", "issue": "概念边界不清，混淆了相近术语"},
            {"index": 2, "thought": "代入答案并检查", "verdict": "失效", "issue": "错误概念导致后续推理全部偏离"},
        ]
        error_step = 0
    elif category == "method":
        steps = [
            {"index": 0, "thought": "读题并识别题型", "verdict": "正确", "issue": ""},
            {"index": 1, "thought": "选择解题方法", "verdict": "偏离", "issue": "方法选择错误，未匹配题目结构"},
            {"index": 2, "thought": "执行步骤并计算", "verdict": "失效", "issue": "方法错误导致步骤无法推进"},
            {"index": 3, "thought": "检查结果是否合理", "verdict": "缺失", "issue": "没有回看结果与题目条件是否一致"},
        ]
        error_step = 1
    elif category == "careless":
        steps = [
            {"index": 0, "thought": "读题并提取条件", "verdict": "正确", "issue": ""},
            {"index": 1, "thought": "计算与书写", "verdict": "正确", "issue": ""},
            {"index": 2, "thought": "检查单位、符号与关键条件", "verdict": "缺失", "issue": "跳过了最后 10 秒检查，细节出错"},
        ]
        error_step = 2
    else:
        steps = [
            {"index": 0, "thought": "读题并判断难度", "verdict": "偏离", "issue": "在难题上停留过久，未及时标记跳过"},
            {"index": 1, "thought": "尝试解题", "verdict": "失效", "issue": "时间不足导致未完成"},
            {"index": 2, "thought": "检查剩余题目", "verdict": "缺失", "issue": "没有为简单题保留时间"},
        ]
        error_step = 0
    return {
        "steps": steps,
        "error_step": error_step,
        "summary": f"错误发生在第 {error_step + 1} 步：{steps[error_step]['issue']}。",
    }


async def get_or_create_trace(
    db: Session, user: User, goal: Goal, mistake: Mistake
) -> ThoughtTrace:
    existing = db.scalar(select(ThoughtTrace).where(ThoughtTrace.mistake_id == mistake.id))
    if existing:
        return existing

    data = None
    engine = "rule"
    if llm.available:
        system = (
            "你是思维路径回放器。请把学生这道错题的解题过程拆成 3-5 个思维步骤，"
            "指出错误发生在哪一步、为什么。输出 JSON："
            '{"steps":[{"index":0,"thought":"这一步在想什么","verdict":"正确|偏离|缺失|失效","issue":"问题"}],'
            '"error_step":0,"summary":"一句话总结"}。只输出 JSON。'
        )
        prompt = (
            f"题目：{mistake.question}\n学生答案：{mistake.user_answer or '未作答'}\n"
            f"正确答案：{mistake.correct_answer or '未提供'}\n错因：{mistake.category_label}\n"
            f"补救建议：{mistake.suggestion}"
        )
        candidate = await llm.chat_json(system, prompt)
        if isinstance(candidate, dict) and isinstance(candidate.get("steps"), list):
            steps = []
            for index, item in enumerate(candidate["steps"][:6]):
                if not isinstance(item, dict):
                    continue
                steps.append(
                    {
                        "index": index,
                        "thought": str(item.get("thought", ""))[:200],
                        "verdict": str(item.get("verdict", "正确"))[:8],
                        "issue": str(item.get("issue", ""))[:200],
                    }
                )
            error_step = candidate.get("error_step", 0)
            if steps and isinstance(error_step, int) and 0 <= error_step < len(steps):
                data = {
                    "steps": steps,
                    "error_step": error_step,
                    "summary": str(candidate.get("summary", ""))[:300],
                }
                engine = "llm"
    if data is None:
        data = _fallback(mistake)

    trace = ThoughtTrace(
        user_id=user.id,
        goal_id=goal.id,
        mistake_id=mistake.id,
        steps=json.dumps(data["steps"], ensure_ascii=False),
        error_step=data["error_step"],
        summary=data["summary"],
        engine=engine,
    )
    db.add(trace)
    record_evidence(
        db,
        user.id,
        goal.id,
        "thought_trace",
        mistake.question[:60],
        {
            "mistake_id": mistake.id,
            "category": mistake.category,
            "error_step": data["error_step"],
            "steps": data["steps"],
        },
        data["summary"],
        engine=engine,
    )
    db.commit()
    db.refresh(trace)
    return trace


def trace_to_dict(trace: ThoughtTrace) -> Dict:
    try:
        steps = json.loads(trace.steps)
    except Exception:
        steps = []
    return {
        "mistake_id": trace.mistake_id,
        "error_step": trace.error_step,
        "summary": trace.summary,
        "steps": steps,
        "engine": trace.engine,
    }