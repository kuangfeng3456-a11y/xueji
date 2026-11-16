"""华为云实例状态：真实调用 RDS / DCS 查询接口，返回云端确认的实例状态。

凭证来自环境变量（由 .env.cloud 加载），不在此文件硬编码。
查询失败时如实返回错误，不伪造实例状态。
"""

import os
import time
from typing import Dict, List

REGION = os.getenv("CLOUD_REGION", "cn-north-4")


def _credentials():
    ak = os.getenv("HUAWEICLOUD_SDK_AK")
    sk = os.getenv("HUAWEICLOUD_SDK_SK")
    project = os.getenv("CLOUD_PROJECT_ID")
    return ak, sk, project


def _clients():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkcore.region.region import Region
    from huaweicloudsdkrds.v3 import RdsClient
    from huaweicloudsdkdcs.v2 import DcsClient

    ak, sk, project = _credentials()
    credentials = BasicCredentials(ak, sk, project)
    rds_region = Region(REGION, f"https://rds.{REGION}.myhuaweicloud.com")
    dcs_region = Region(REGION, f"https://dcs.{REGION}.myhuaweicloud.com")
    rds = RdsClient.new_builder().with_credentials(credentials).with_region(rds_region).build()
    dcs = DcsClient.new_builder().with_credentials(credentials).with_region(dcs_region).build()
    return rds, dcs


def _dump(model) -> Dict:
    if model is None:
        return {}
    if hasattr(model, "to_dict"):
        try:
            return model.to_dict()
        except Exception:
            return {}
    return {}


def _pick(data: Dict, *names):
    for name in names:
        value = data.get(name)
        if value not in (None, "", []):
            return value
    return None


def _rds_items(rds) -> Dict:
    from huaweicloudsdkrds.v3.model import ListInstancesRequest

    try:
        response = rds.list_instances(ListInstancesRequest())
    except Exception as exc:
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"[:160]}

    items: List[Dict] = []
    for raw in getattr(response, "instances", None) or []:
        data = _dump(raw)
        items.append(
            {
                "id": _pick(data, "id"),
                "name": _pick(data, "name"),
                "status": _pick(data, "status"),
                "type": _pick(data, "type"),
                "public_ips": _pick(data, "public_ips") or [],
                "private_ips": _pick(data, "private_ips") or [],
                "port": _pick(data, "port"),
                "datastore": _pick(data, "datastore"),
            }
        )
    return {"items": items, "error": ""}


def _dcs_items(dcs) -> Dict:
    from huaweicloudsdkdcs.v2.model import ListInstancesRequest as DcsListInstancesRequest

    try:
        response = dcs.list_instances(DcsListInstancesRequest())
    except Exception as exc:
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"[:160]}

    items: List[Dict] = []
    for raw in getattr(response, "instances", None) or []:
        data = _dump(raw)
        items.append(
            {
                "id": _pick(data, "instance_id", "id"),
                "name": _pick(data, "name"),
                "status": _pick(data, "status"),
                "capacity": _pick(data, "capacity"),
                "ip": _pick(data, "ip"),
                "port": _pick(data, "port"),
                "public_ip": _pick(data, "publicip_address", "public_ip_address"),
                "engine": _pick(data, "engine"),
            }
        )
    return {"items": items, "error": ""}


def cloud_instances() -> Dict:
    """同步查询云端实例状态；无凭证或 SDK 不可用时如实返回不可用。"""
    ak, sk, project = _credentials()
    result = {
        "configured": bool(ak and sk and project),
        "region": REGION,
        "rds": {"items": [], "error": ""},
        "dcs": {"items": [], "error": ""},
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "detail": "",
    }
    if not result["configured"]:
        result["detail"] = "未配置华为云凭证（HUAWEICLOUD_SDK_AK / SK / CLOUD_PROJECT_ID）"
        return result

    try:
        rds, dcs = _clients()
    except Exception as exc:
        result["detail"] = f"云客户端初始化失败：{type(exc).__name__}: {exc}"[:200]
        return result

    result["rds"] = _rds_items(rds)
    result["dcs"] = _dcs_items(dcs)

    rds_states = [item["status"] for item in result["rds"]["items"] if item.get("status")]
    dcs_states = [item["status"] for item in result["dcs"]["items"] if item.get("status")]
    result["detail"] = (
        f"RDS {len(rds_states)} 个实例：{'/'.join(rds_states) or '无'}；"
        f"DCS {len(dcs_states)} 个实例：{'/'.join(dcs_states) or '无'}"
    )
    return result