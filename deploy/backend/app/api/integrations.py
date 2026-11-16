from typing import List

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..models import User
from ..services.huawei_cloud import cloud_instances
from ..services.integrations import describe_integrations, test_integrations

router = APIRouter(prefix="/integrations", tags=["接入状态"])


@router.get("/cloud")
def cloud(user: User = Depends(get_current_user)) -> dict:
    return cloud_instances()


@router.get("")
def integrations(user: User = Depends(get_current_user)) -> dict:
    return describe_integrations()


@router.post("/test")
async def run_integration_tests(
    force: bool = False, user: User = Depends(get_current_user)
) -> dict:
    results = await test_integrations(force=force)
    configured = len([item for item in results if item["configured"]])
    healthy = len([item for item in results if item["status"] in ("ok", "client")])
    degraded = len([item for item in results if item["status"] == "degraded"])
    return {
        "items": results,
        "status": "degraded" if degraded else "ok",
        "configured_count": configured,
        "healthy_count": healthy,
        "degraded_count": degraded,
        "total": len(results),
        "tested_at": None,
    }