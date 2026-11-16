"""提示词评测用例（文档 6.6 / 附录 B eval_cases）。

启动时按提示词库的示例各生成一条常规用例，保证「每个提示词都有评测样本」；
后续可在其中追加边界与对抗用例（tags=boundary/adversarial）。
"""

import hashlib
import json
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import EvalCase
from ..prompts import library


def _case_id(prompt_id: str, tag: str) -> str:
    return f"case_{prompt_id.lower()}_{tag}"


def seed_eval_cases(db: Session, prompt_id: Optional[str] = None) -> Dict[str, int]:
    """幂等写入：每个提示词一条常规用例（输入为占位符样例，期望为合法信封）。"""
    created = 0
    for pid in sorted(library.PROMPTS):
        if prompt_id and pid != prompt_id:
            continue
        item = library.PROMPTS[pid]
        if not item["user_template"]:
            continue
        case_id = _case_id(pid, "normal")
        exists = db.scalar(select(EvalCase).where(EvalCase.case_id == case_id))
        sample = library.sample_output(pid)
        expected = json.dumps(sample, ensure_ascii=False) if sample else "valid_envelope"
        payload = json.dumps(
            {name: "{{" + name + "}}" for name in library.placeholders(pid)},
            ensure_ascii=False,
        )
        if exists:
            if exists.expected != expected:
                exists.expected = expected
            continue
        db.add(
            EvalCase(
                case_id=case_id,
                prompt_id=pid,
                input=payload,
                expected=expected[:4000],
                tags="normal",
            )
        )
        created += 1
    db.commit()
    total = db.scalar(select(func.count(EvalCase.id))) or 0
    return {"created": created, "total": int(total)}


def list_cases(db: Session, prompt_id: str = "", tag: str = "", limit: int = 100) -> List[Dict]:
    query = select(EvalCase).order_by(EvalCase.prompt_id, EvalCase.case_id).limit(limit)
    if prompt_id:
        query = query.where(EvalCase.prompt_id == prompt_id.strip().upper())
    if tag:
        query = query.where(EvalCase.tags == tag)
    rows = db.scalars(query).all()
    return [
        {
            "case_id": row.case_id,
            "prompt_id": row.prompt_id,
            "tags": row.tags,
            "input_hash": hashlib.sha256(row.input.encode("utf-8")).hexdigest()[:12],
            "expected_preview": row.expected[:160],
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
