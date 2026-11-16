"""华为云 RDS MySQL / DCS Redis 快速开通脚本。

用法：
    python scripts/provision_cloud.py --dry-run        # 只打印开通计划，不创建资源
    python scripts/provision_cloud.py --apply          # 真实创建（会产生计费资源）
    python scripts/provision_cloud.py --apply --rds-only
    python scripts/provision_cloud.py --apply --redis-only

必须的环境变量：
    HUAWEICLOUD_SDK_AK / HUAWEICLOUD_SDK_SK / CLOUD_PROJECT_ID
    CLOUD_REGION（默认 cn-north-4）
    CLOUD_VPC_ID / CLOUD_SUBNET_ID / CLOUD_SECURITY_GROUP_ID
可选：
    RDS_FLAVOR（不填自动查询最小 MySQL 8.0 单机规格）
    RDS_VOLUME_SIZE（默认 40GB）、RDS_PASSWORD、RDS_NAME
    DCS_SPEC_CODE（Redis 规格编码，必填）、DCS_CAPACITY（默认 1GB）、DCS_PASSWORD
"""

import argparse
import os
import secrets
import string
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_CLOUD = ROOT / ".env.cloud"

sys.path.insert(0, str(ROOT))
from app.config import _load_env_files  # noqa: E402

_load_env_files()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def need(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f"缺少环境变量 {name}")
    return value


def gen_password() -> str:
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*"]
    chars = "".join(pools)
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(16))
        if all(any(char in pool for char in pwd) for pool in pools):
            return pwd


def region_name() -> str:
    return env("CLOUD_REGION", "cn-north-4")


def az_name(region: str) -> str:
    return env("CLOUD_AVAILABILITY_ZONE", f"{region}a")


def write_cloud_env(values: dict) -> None:
    lines = ["# 由 scripts/provision_cloud.py 生成，请勿提交版本库"]
    for key, value in values.items():
        lines.append(f"{key}={value}")
    ENV_CLOUD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n连接信息已写入 {ENV_CLOUD}")
    print("请合并到 backend/.env 或项目根 .env 后重启服务。")


def dry_run(args) -> None:
    region = region_name()
    az = az_name(region)
    print("==== 华为云 RDS / DCS 开通计划 ====")
    print(f"区域: {region}  可用区: {az}")
    print(f"项目 ID: {'已配置' if env('CLOUD_PROJECT_ID') else '未配置'}")
    print(
        "AK/SK: "
        + ("已配置" if env("HUAWEICLOUD_SDK_AK") and env("HUAWEICLOUD_SDK_SK") else "未配置")
    )
    print(f"VPC: {env('CLOUD_VPC_ID') or '未配置'}")
    print(f"子网: {env('CLOUD_SUBNET_ID') or '未配置'}")
    print(f"安全组: {env('CLOUD_SECURITY_GROUP_ID') or '未配置'}")
    if not args.redis_only:
        print(
            f"RDS MySQL 8.0 单机 · {env('RDS_VOLUME_SIZE', '40')}GB · "
            f"规格: {env('RDS_FLAVOR') or '自动选择最小规格'}"
        )
    if not args.rds_only:
        print(
            f"DCS Redis 5.0 · {env('DCS_CAPACITY', '1')}GB · "
            f"规格: {env('DCS_SPEC_CODE') or '未配置（需从控制台获取 spec_code）'}"
        )
    missing = [
        key
        for key in (
            "HUAWEICLOUD_SDK_AK",
            "HUAWEICLOUD_SDK_SK",
            "CLOUD_PROJECT_ID",
            "CLOUD_VPC_ID",
            "CLOUD_SUBNET_ID",
            "CLOUD_SECURITY_GROUP_ID",
        )
        if not env(key)
    ]
    if missing:
        print("\n缺少: " + ", ".join(missing))
    print("\n实际开通：设置上述变量后执行 python scripts/provision_cloud.py --apply")
    print("注意：会创建计费资源；RDS 默认 40GB SSD 单机，DCS 默认 1GB。")


def clients():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkrds.v3 import RdsClient
    from huaweicloudsdkdcs.v2 import DcsClient

    credentials = BasicCredentials(
        need("HUAWEICLOUD_SDK_AK"), need("HUAWEICLOUD_SDK_SK"), need("CLOUD_PROJECT_ID")
    )
    region = region_name()
    rds = RdsClient.new_builder().with_credentials(credentials).with_region(region).build()
    dcs = DcsClient.new_builder().with_credentials(credentials).with_region(region).build()
    return rds, dcs


def wait_rds(rds, instance_id: str, timeout: int) -> str:
    from huaweicloudsdkrds.v3.model import ListInstancesRequest

    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = rds.list_instances(ListInstancesRequest(id=instance_id))
        for item in getattr(resp, "instances", None) or []:
            status = getattr(item, "status", "")
            print(f"RDS {instance_id} 状态: {status}")
            if status == "ACTIVE":
                ips = getattr(item, "public_ips", None) or getattr(item, "private_ips", None) or []
                return ips[0] if ips else ""
        time.sleep(15)
    raise SystemExit("等待 RDS 可用超时；请到控制台确认实例状态")


def ensure_rds(rds, args) -> dict:
    from huaweicloudsdkrds.v3.model import (
        BackupStrategy,
        CreateInstanceRequest,
        Datastore,
        Ha,
        InstanceRequest,
        ListFlavorsRequest,
        Volume,
    )

    region = region_name()
    az = az_name(region)
    flavor = env("RDS_FLAVOR")
    if not flavor:
        resp = rds.list_flavors(
            ListFlavorsRequest(database_name="MySQL", version_name="8.0")
        )
        flavors = [
            item
            for item in (resp.flavors or [])
            if getattr(item, "instance_mode", "") in ("Single", "single")
        ] or list(resp.flavors or [])
        flavors.sort(
            key=lambda item: (
                getattr(item, "vcpus", 99) or 99,
                getattr(item, "ram", 9999) or 9999,
            )
        )
        if not flavors:
            raise SystemExit("未查询到 MySQL 8.0 规格，请设置 RDS_FLAVOR")
        flavor = flavors[0].spec_code
        print(
            f"自动选择 RDS 规格: {flavor} "
            f"（{getattr(flavors[0], 'vcpus', '?')}C/{getattr(flavors[0], 'ram', '?')}G）"
        )

    password = env("RDS_PASSWORD") or gen_password()
    body = InstanceRequest(
        name=env("RDS_NAME", "xueji-mysql"),
        datastore=Datastore(type="MySQL", version="8.0"),
        ha=Ha(mode="single"),
        port=int(env("RDS_PORT", "3306")),
        password=password,
        backup_strategy=BackupStrategy(start_time="02:00-03:00", keep_days=7),
        flavor_ref=flavor,
        volume=Volume(type="CLOUDSSD", size=int(env("RDS_VOLUME_SIZE", "40"))),
        region=region,
        availability_zone=az,
        vpc_id=need("CLOUD_VPC_ID"),
        subnet_id=need("CLOUD_SUBNET_ID"),
        security_group_id=need("CLOUD_SECURITY_GROUP_ID"),
        enterprise_project_id="0",
    )
    resp = rds.create_instance(CreateInstanceRequest(body=body))
    item = getattr(resp, "instance", None)
    instance_id = getattr(item, "id", None) if item else getattr(resp, "instance_id", None)
    if not instance_id:
        raise SystemExit(
            f"RDS 创建响应异常: {resp.to_dict() if hasattr(resp, 'to_dict') else resp}"
        )
    print(f"RDS 实例已提交: {instance_id}")
    host = wait_rds(rds, instance_id, args.timeout)
    return {
        "RDS_HOST": host,
        "RDS_PORT": env("RDS_PORT", "3306"),
        "RDS_USER": "root",
        "RDS_PASSWORD": password,
        "RDS_DATABASE": env("RDS_DATABASE", "xueji"),
        "RDS_NAME": env("RDS_NAME", "xueji-mysql"),
    }


def wait_dcs(dcs, instance_id: str, timeout: int):
    from huaweicloudsdkdcs.v2.model import ShowInstanceRequest

    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = dcs.show_instance(ShowInstanceRequest(instance_id=instance_id))
        status = getattr(resp, "status", "")
        print(f"DCS {instance_id} 状态: {status}")
        if status in ("RUNNING", "SUCCESS"):
            ip = getattr(resp, "ip", None) or getattr(resp, "publicip_address", None)
            port = getattr(resp, "port", None)
            return ip, port
        time.sleep(15)
    raise SystemExit("等待 DCS 可用超时；请到控制台确认实例状态")


def ensure_redis(dcs, args) -> dict:
    from huaweicloudsdkdcs.v2.model import CreateInstanceBody, CreateInstanceRequest

    spec = env("DCS_SPEC_CODE")
    if not spec:
        raise SystemExit("缺少 DCS_SPEC_CODE：请到 DCS 控制台查看 Redis 规格编码后设置")
    password = env("DCS_PASSWORD") or gen_password()
    body = CreateInstanceBody(
        name=env("DCS_NAME", "xueji-redis"),
        engine="Redis",
        engine_version="5.0",
        capacity=int(env("DCS_CAPACITY", "1")),
        spec_code=spec,
        az_codes=[az_name(region_name())],
        vpc_id=need("CLOUD_VPC_ID"),
        subnet_id=need("CLOUD_SUBNET_ID"),
        security_group_id=need("CLOUD_SECURITY_GROUP_ID"),
        password=password,
        enterprise_project_id="0",
    )
    resp = dcs.create_instance(CreateInstanceRequest(body=body))
    instances = getattr(resp, "instances", None) or []
    instance_id = (
        getattr(instances[0], "instance_id", None) if instances else None
    ) or getattr(resp, "instance_id", None)
    if not instance_id:
        raise SystemExit(
            f"DCS 创建响应异常: {resp.to_dict() if hasattr(resp, 'to_dict') else resp}"
        )
    print(f"DCS 实例已提交: {instance_id}")
    ip, port = wait_dcs(dcs, instance_id, args.timeout)
    return {
        "REDIS_HOST": ip or "",
        "REDIS_PORT": str(port or 6379),
        "REDIS_PASSWORD": password,
        "REDIS_DB": "0",
        "DCS_NAME": env("DCS_NAME", "xueji-redis"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="开通华为云 RDS MySQL / DCS Redis")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不创建资源")
    parser.add_argument("--apply", action="store_true", help="真实创建资源")
    parser.add_argument("--rds-only", action="store_true")
    parser.add_argument("--redis-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=1800, help="等待实例可用的秒数")
    args = parser.parse_args()

    if args.dry_run or not args.apply:
        dry_run(args)
        return

    rds, dcs = clients()
    values = {}
    if not args.redis_only:
        values.update(ensure_rds(rds, args))
    if not args.rds_only:
        values.update(ensure_redis(dcs, args))
    write_cloud_env(values)
    print("开通完成。下一步：")
    print("  1. 将 .env.cloud 合并到 .env，并设置 CLOUD_REGION/CLOUD_PROJECT_ID")
    print("  2. python scripts/migrate_to_rds.py --dry-run")
    print("  3. python scripts/migrate_to_rds.py --apply")
    print("  4. 重启服务，在「系统接入」页验证 RDS / DCS Redis")


if __name__ == "__main__":
    main()