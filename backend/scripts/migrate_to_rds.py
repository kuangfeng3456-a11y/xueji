"""把 SQLite 开发库迁移到华为云 RDS MySQL。

用法：
    set TARGET_DATABASE_URL=mysql+pymysql://user:pass@host:3306/xueji?charset=utf8mb4
    python scripts/migrate_to_rds.py --dry-run
    python scripts/migrate_to_rds.py --apply
    python scripts/migrate_to_rds.py --apply --truncate   # 先清空目标表，谨慎

SOURCE_DATABASE_URL 默认使用 backend/xueji.db。
"""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Base  # noqa: E402
from app import models as _models  # noqa: E402,F401  确保表注册到 Base.metadata
from app.config import settings  # noqa: E402

BATCH_SIZE = 500


def source_url() -> str:
    return os.getenv(
        "SOURCE_DATABASE_URL",
        f"sqlite:///{(ROOT / 'xueji.db').as_posix()}",
    )


def target_url() -> str:
    value = os.getenv("TARGET_DATABASE_URL", "").strip()
    if value:
        return value
    return settings.DATABASE_URL


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite -> 华为云 RDS MySQL 迁移")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--truncate", action="store_true", help="迁移前清空目标表")
    args = parser.parse_args()

    source = source_url()
    target = target_url()
    print(f"源数据库: {source}")
    print(f"目标数据库: {target}")

    source_engine = create_engine(source)
    tables = list(Base.metadata.sorted_tables)

    if args.dry_run:
        with source_engine.connect() as connection:
            total = 0
            for table in tables:
                count = connection.execute(select(func.count()).select_from(table)).scalar()
                total += count or 0
                print(f"  {table.name:24s} {count}")
            print(f"合计 {total} 行；未连接目标数据库。")
        return

    if target.startswith("sqlite") or target == source:
        raise SystemExit("目标必须是 MySQL/RDS，请设置 TARGET_DATABASE_URL 或 RDS_* 环境变量")

    if not args.apply:
        print("未执行。使用 --apply 真正写入目标库。")
        return

    target_engine = create_engine(target, pool_pre_ping=True)
    Base.metadata.create_all(target_engine)
    print("目标表已创建/确认。")

    with source_engine.connect() as src, target_engine.begin() as dst:
        if args.truncate:
            for table in reversed(tables):
                dst.execute(table.delete())
            print("已清空目标表。")

        for table in tables:
            rows = src.execute(select(table)).mappings().all()
            if not rows:
                print(f"  {table.name:24s} 0")
                continue
            for start in range(0, len(rows), BATCH_SIZE):
                batch = [dict(row) for row in rows[start : start + BATCH_SIZE]]
                dst.execute(insert(table), batch)
            print(f"  {table.name:24s} {len(rows)}")

    print("迁移完成，开始校验行数...")
    failures = []
    with source_engine.connect() as src, target_engine.connect() as dst:
        for table in tables:
            source_count = src.execute(select(func.count()).select_from(table)).scalar() or 0
            target_count = dst.execute(select(func.count()).select_from(table)).scalar() or 0
            flag = "OK" if source_count == target_count else "DIFF"
            if flag == "DIFF":
                failures.append(table.name)
            print(f"  {flag:4s} {table.name:24s} {source_count} -> {target_count}")
    if failures:
        raise SystemExit(f"行数不一致: {', '.join(failures)}")
    print("迁移校验通过。")


if __name__ == "__main__":
    main()