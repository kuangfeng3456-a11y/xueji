"""管理员重置密码（没有邮件/短信通道时的兜底手段）。

用户在登录页选择「忘记密码」后，如果既没有设置密保问题、也没有保存恢复码，
就只能由运营/管理员在服务器上执行本脚本，重置为一个随机密码并当面告知，
同时让该账号在所有设备上下线。

用法：
    python scripts/reset_password.py <用户名>
    python scripts/reset_password.py <用户名> --password <新密码>
"""

import argparse
import secrets
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.account_security import revoke_all_sessions  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="重置指定账号的登录密码，并让其全部设备下线")
    parser.add_argument("username", help="要重置的用户名")
    parser.add_argument("--password", default="", help="指定新密码；留空则随机生成")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username.strip()))
        if not user:
            print(f"未找到用户：{args.username}")
            return 1
        new_password = args.password.strip() or secrets.token_urlsafe(9)
        user.password_hash = hash_password(new_password)
        db.commit()
        revoked = revoke_all_sessions(db, user.id, reason="admin_reset")
        print(f"已重置 {user.username} 的密码：{new_password}")
        print(f"已让 {revoked} 个在线会话下线。请通过安全渠道把新密码告知用户。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
