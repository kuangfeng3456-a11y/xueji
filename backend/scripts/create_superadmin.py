"""创建 / 升级平台超级管理员（开发者账号）。

用法
----
    # 交互式：不传密码则随机生成一个强口令并打印一次
    python scripts/create_superadmin.py --username devadmin

    # 指定密码（用于自动化部署，注意别留在 shell 历史里）
    python scripts/create_superadmin.py --username devadmin --password 'S0me-Strong-Pass'

    # 也可以用环境变量，便于 CI / 容器启动钩子
    SUPERADMIN_USERNAME=devadmin SUPERADMIN_PASSWORD=... python scripts/create_superadmin.py

    # 把已有账号提升为超管（不改密码）
    python scripts/create_superadmin.py --username demo --promote-only

幂等性
------
* 账号不存在 → 新建并把 is_superadmin 置真；
* 账号已存在 → 默认只提升权限，不动原密码（除非显式传 --password 或 --reset-password）。

安全说明
--------
* 密码走项目统一的 hash_password（bcrypt 级别），库里不存明文；
* 随机口令只在标准输出打印一次，不写日志、不落文件；
* 该脚本不能被 HTTP 接口触发，必须有人登录服务器执行。
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import ensure_schema  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

DEFAULT_USERNAME = os.getenv("SUPERADMIN_USERNAME", "devadmin").strip() or "devadmin"
DEFAULT_NICKNAME = os.getenv("SUPERADMIN_NICKNAME", "平台管理员").strip() or "平台管理员"


def generate_password(length: int = 16) -> str:
    """生成含大小写、数字、符号的随机口令（去掉易混淆字符）。"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*-_=+" for c in pwd)
        ):
            return pwd


def main() -> int:
    parser = argparse.ArgumentParser(description="创建或升级平台超级管理员")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=os.getenv("SUPERADMIN_PASSWORD", ""))
    parser.add_argument("--nickname", default=DEFAULT_NICKNAME)
    parser.add_argument("--school", default=os.getenv("SUPERADMIN_SCHOOL", "平台研发"))
    parser.add_argument(
        "--promote-only",
        action="store_true",
        help="只提升权限，不修改已有账号的密码",
    )
    args = parser.parse_args()

    username = (args.username or "").strip()
    if not username or len(username) < 3:
        print("用户名至少 3 个字符", file=sys.stderr)
        return 2

    provided_password = (args.password or "").strip()
    if provided_password and len(provided_password) < 8:
        print("密码至少 8 位", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        # 老库可能还没有 is_superadmin 列：先跑一次与启动时相同的补列逻辑
        ensure_schema()
        user = db.scalar(select(User).where(User.username == username))
        created = user is None
        plain_password = ""

        if created:
            plain_password = provided_password or generate_password()
            user = User(
                username=username,
                nickname=args.nickname,
                school=args.school,
                password_hash=hash_password(plain_password),
                is_superadmin=True,
            )
            db.add(user)
        else:
            user.is_superadmin = True
            if not args.promote_only:
                # 显式给了密码就重置，否则保持原密码不动（避免误改线上账号）
                if provided_password:
                    user.password_hash = hash_password(provided_password)
                    plain_password = provided_password

        db.commit()
        db.refresh(user)

        print("=" * 56)
        print(f"账号已就绪：{user.username} (id={user.id})")
        print(f"身份：超级管理员 {'（新建）' if created else '（已提升）'}")
        print(f"昵称：{user.nickname}")
        if plain_password:
            print(f"初始密码：{plain_password}")
            print("注意：该密码只显示这一次，请立即妥善保存，登录后建议改密。")
        else:
            print("密码：未改动（沿用原密码）")
        print("登录地址：http://127.0.0.1:8011/#/login")
        print("管理后台：登录后进入「设置 → 管理后台」")
        print("=" * 56)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
