"""AI 可靠性评测中心：基准题集、真实模型调用、可复算评分与版本记录。"""

import time
import uuid
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import llm
from ..models import EvalRun, User

BASE_CASES = [
    {
        "id": "math-int",
        "subject": "数学",
        "question": "计算定积分 ∫_0^1 2x dx，只给出结果。",
        "reference": "1",
        "keywords": ["1"],
    },
    {
        "id": "math-limit",
        "subject": "数学",
        "question": "当 x 趋近于 0 时，sin x / x 的极限是多少？只给出结果。",
        "reference": "1",
        "keywords": ["1"],
    },
    {
        "id": "math-deriv",
        "subject": "数学",
        "question": "函数 y=x^3 在 x=1 处的导数是多少？只给出结果。",
        "reference": "3",
        "keywords": ["3"],
    },
    {
        "id": "english-main",
        "subject": "英语",
        "question": "四级听力篇章中，理解主旨大意最有效的方法是什么？用一句话回答。",
        "reference": "先看题干预测主题，关注开头与结尾的总结",
        "keywords": ["主旨", "开头", "结尾", "总结", "题干"],
    },
    {
        "id": "english-word",
        "subject": "英语",
        "question": "单词 abandon 的中文含义是什么？只给出中文。",
        "reference": "放弃，抛弃",
        "keywords": ["放弃", "抛弃", "丢弃"],
    },
    {
        "id": "cs-404",
        "subject": "计算机",
        "question": "HTTP 状态码 404 表示什么？用一句话回答。",
        "reference": "请求的资源未找到",
        "keywords": ["未找到", "不存在", "not found", "找不到"],
    },
]


def _match(answer: str, keywords: List[str]) -> bool:
    text = (answer or "").lower()
    return any(keyword.lower() in text for keyword in keywords)


async def run_eval(db: Session, user: User, limit: int = 6) -> Dict:
    cases = BASE_CASES[: max(1, min(limit, len(BASE_CASES)))]
    run_id = uuid.uuid4().hex[:16]
    results = []
    correct = 0
    failures = 0
    total_latency = 0
    engine = "llm" if llm.available else "rule"
    model_version = llm.model if llm.available else ""

    for case in cases:
        started = time.perf_counter()
        answer = None
        status = "ok"
        if llm.available:
            answer = await llm.chat(
                "你是严谨的学科问答助手，只输出简短答案。",
                case["question"],
                temperature=0.1,
                max_tokens=200,
            )
        latency = int((time.perf_counter() - started) * 1000)
        total_latency += latency
        if answer is None:
            failures += 1
            status = "failed" if llm.available else "skipped"
            answer = ""
        passed = _match(answer, case["keywords"])
        if passed:
            correct += 1
        results.append(
            {
                "case_id": case["id"],
                "subject": case["subject"],
                "question": case["question"],
                "reference": case["reference"],
                "answer": (answer or "")[:300],
                "passed": passed,
                "latency_ms": latency,
                "status": status,
            }
        )

    total = len(cases)
    accuracy = round(correct / total, 3) if total else 0.0
    avg_latency = int(total_latency / total) if total else 0
    row = EvalRun(
        user_id=user.id,
        run_id=run_id,
        cases=total,
        correct=correct,
        accuracy=accuracy,
        avg_latency_ms=avg_latency,
        failures=failures,
        engine=engine,
        model_version=model_version,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "run_id": run_id,
        "cases": results,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "avg_latency_ms": avg_latency,
        "failures": failures,
        "engine": engine,
        "model_version": model_version,
        "cost_note": "成本按调用次数估算，未接入计费 API。",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "note": "" if llm.available else "模型未配置，本次仅记录题集，不作正确性结论。",
    }


def list_runs(db: Session, user: User, limit: int = 20) -> List[Dict]:
    rows = db.scalars(
        select(EvalRun)
        .where(EvalRun.user_id == user.id)
        .order_by(EvalRun.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "run_id": row.run_id,
            "cases": row.cases,
            "correct": row.correct,
            "accuracy": row.accuracy,
            "avg_latency_ms": row.avg_latency_ms,
            "failures": row.failures,
            "engine": row.engine,
            "model_version": row.model_version,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]