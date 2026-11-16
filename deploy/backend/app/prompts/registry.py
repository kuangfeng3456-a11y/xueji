"""提示词版本注册表（文档 6.6）：把 P00–P18 写入 prompt_versions。

提示词正文的哈希变化即视为内容变更：同一个 version 下哈希不同会被记录下来，
便于「提示词即代码」的回归与回滚（PROMPT_VERSION_PIN 可固定版本）。
"""

import logging
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PromptVersion
from .library import PROMPTS, prompt_hash

logger = logging.getLogger("xueji.prompts")


def sync_prompt_versions(db: Session) -> Dict[str, int]:
    """幂等同步：新增缺失版本、刷新哈希变更的旧行，返回统计。"""
    created = updated = unchanged = 0
    for prompt_id in sorted(PROMPTS):
        item = PROMPTS[prompt_id]
        digest = prompt_hash(prompt_id)
        row = db.scalar(
            select(PromptVersion).where(
                PromptVersion.prompt_id == prompt_id,
                PromptVersion.version == item["version"],
            )
        )
        if row is None:
            db.add(
                PromptVersion(
                    prompt_id=prompt_id,
                    version=item["version"],
                    hash=digest,
                    tier=item["tier"] or "prefix",
                    system_text=item["system"],
                    user_template=item["user_template"],
                    output_contract=item["output_contract"],
                    status="active",
                )
            )
            created += 1
        elif row.hash != digest:
            row.hash = digest
            row.tier = item["tier"] or "prefix"
            row.system_text = item["system"]
            row.user_template = item["user_template"]
            row.output_contract = item["output_contract"]
            updated += 1
        else:
            unchanged += 1
    db.commit()
    stats = {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "total": len(PROMPTS),
    }
    logger.info("提示词版本同步完成：%s", stats)
    return stats


def list_versions(db: Session, prompt_id: str = "") -> List[Dict]:
    """注册表内容（不含正文），供提示词中心展示。"""
    query = select(PromptVersion).order_by(PromptVersion.prompt_id, PromptVersion.version)
    if prompt_id:
        query = query.where(PromptVersion.prompt_id == prompt_id.strip().upper())
    rows = db.scalars(query).all()
    return [
        {
            "prompt_id": row.prompt_id,
            "version": row.version,
            "hash": row.hash,
            "tier": row.tier,
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]
