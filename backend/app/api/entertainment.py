from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..models import User
from ..services import entertainment

router = APIRouter(prefix="/entertainment", tags=["娱乐内容"])


@router.get("/kinds")
def kinds(user: User = Depends(get_current_user)) -> dict:
    return {"kinds": entertainment.KINDS, "total": len(entertainment.KINDS)}


@router.get("/{kind}")
async def content(
    kind: str,
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
) -> dict:
    if kind not in entertainment.KIND_MAP:
        raise HTTPException(status_code=404, detail="不支持的内容类型")
    result = await entertainment.fetch(kind, force=force)
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=f"外部内容源暂不可用：{result.get('error', '')}")
    return result