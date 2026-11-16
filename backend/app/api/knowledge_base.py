from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..models import User
from ..services import knowledge_base

router = APIRouter(prefix="/knowledge-base", tags=["外部知识库"])


@router.get("/probe")
async def probe(user: User = Depends(get_current_user)) -> dict:
    results = await knowledge_base.probe(force=True)
    available = len([item for item in results if item["status"] == "ok"])
    return {
        "sources": results,
        "available_count": available,
        "total": len(results),
        "status": "ok" if available else "unavailable",
    }


@router.get("/lookup")
async def lookup(
    term: str = Query(..., min_length=1, max_length=80),
    user: User = Depends(get_current_user),
) -> dict:
    cleaned = term.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="查询词不能为空")
    return await knowledge_base.lookup(cleaned)