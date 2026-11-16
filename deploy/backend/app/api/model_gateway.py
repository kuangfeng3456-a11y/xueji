"""模型网关状态接口（D1）：主通道、熔断与调用计量。"""

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..llm import llm
from ..models import User

router = APIRouter(tags=["模型网关"])


@router.get("/model-gateway")
def gateway(user: User = Depends(get_current_user)):
    stats = llm.stats()
    stats["available"] = llm.available
    stats["base_configured"] = bool(llm.base_url and llm.api_key)
    stats["fallback"] = "rule"
    return stats