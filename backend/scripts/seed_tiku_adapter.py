"""把学迹的题库按「知识点 = 课程」灌入 tikuAdapter。

用法::

    python scripts/seed_tiku_adapter.py                # 按库里所有目标的知识点灌库
    python scripts/seed_tiku_adapter.py --dry-run      # 只看要写什么，不发请求
    python scripts/seed_tiku_adapter.py --url http://127.0.0.1:8060

为什么要按知识点建课程
----------------------
tikuAdapter 的 ``course_name`` 是唯一能精确筛选的字段。把课程名设为知识点名
（定积分 / 导数与微分 / 线性代数 …），学迹出题时按知识点名查询，
题库里「定积分」这门课下的题就必然是定积分的题，不会串科目、不会串章节。

英语的阅读 / 听力不灌库：这两类是材料题（整篇文章 / 整段听力脚本配多题），
由模型实时生成文章和音频脚本，题库里的单句式题目撑不起真题形态。

脚本幂等：先读出该课程已有题干，跳过重复题，重复执行不会产生脏数据。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import KnowledgePoint  # noqa: E402
from app.services import question_bank, quiz_material, tiku_bank  # noqa: E402

PLAT_SELF = 99
TYPE_SINGLE = 0


def collect_targets() -> dict:
    """返回 {知识点名: 题目列表}，跳过材料类（阅读/听力）与英文题库。"""
    with SessionLocal() as db:
        points = db.scalars(select(KnowledgePoint)).all()
        exam_of = {}
        from app.models import Goal  # 局部导入，避免循环

        for goal in db.scalars(select(Goal)).all():
            exam_of[goal.id] = goal.exam_name

        targets: dict = {}
        skipped = []
        for point in points:
            name = (point.name or "").strip()
            if not name or name in targets:
                continue
            exam_name = exam_of.get(point.goal_id, "")
            if quiz_material.material_kind([name], exam_name):
                skipped.append((name, "材料题由模型生成文章/听力脚本"))
                continue
            info = question_bank.bank_of(name, "zh")
            if not info or not info.get("size"):
                skipped.append((name, "题库未覆盖"))
                continue
            items = question_bank.pick(name, limit=60, offset=0, language="zh")
            if not items:
                skipped.append((name, "题库取题失败"))
                continue
            targets[name] = items
        return {"targets": targets, "skipped": skipped}


def to_payload(name: str, items: list) -> list:
    payload = []
    for item in items:
        options = [str(opt) for opt in item.get("options") or []]
        answer_index = item.get("answer_index")
        if not options or answer_index is None or not (0 <= int(answer_index) < len(options)):
            continue
        payload.append(
            {
                "question": str(item["question"]).strip(),
                "type": TYPE_SINGLE,
                "options": json.dumps(options, ensure_ascii=False),
                "answer": json.dumps([options[int(answer_index)]], ensure_ascii=False),
                "plat": PLAT_SELF,
                "course_name": name,
                # 解析放进扩展字段，管理后台能直接看到为什么选这个答案
                "extra": str(item.get("explanation") or "")[:500],
            }
        )
    return payload


async def main() -> int:
    parser = argparse.ArgumentParser(description="按知识点把题库灌入 tikuAdapter")
    parser.add_argument("--url", default=settings.TIKU_ADAPTER_URL or "http://127.0.0.1:8060")
    parser.add_argument("--user", default=settings.TIKU_ADAPTER_USER)
    parser.add_argument("--password", default=settings.TIKU_ADAPTER_PASSWORD)
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--limit", type=int, default=0, help="每知识点最多写多少题（0=全部）")
    args = parser.parse_args()

    client = tiku_bank.TikuBankClient(args.url, args.user, args.password)
    health = await client.health()
    print(f"[题库] {args.url} -> {health.get('status')} {health.get('detail') or ''}")
    if health.get("status") != "ok":
        print("[题库] 连不上，先确认 tikuAdapter 已启动（start-tiku.bat）")
        return 2

    data = collect_targets()
    targets, skipped = data["targets"], data["skipped"]
    print(f"[计划] 知识点 {len(targets)} 个，跳过 {len(skipped)} 个")

    total_new = 0
    for name, items in targets.items():
        payload = to_payload(name, items)
        if args.limit > 0:
            payload = payload[: args.limit]
        try:
            existing_rows = await client.list_by_course(name, 100, page=0)
            existing = {str(row.get("question") or "").strip() for row in existing_rows}
        except Exception as exc:  # noqa: BLE001
            print(f"  - {name}: 读取已有题失败 {exc}")
            continue
        fresh = [item for item in payload if item["question"] not in existing]
        if args.dry_run:
            print(f"  - {name}: 现有 {len(existing)}，待写 {len(fresh)}")
            total_new += len(fresh)
            continue
        created = 0
        try:
            created = await client.create(fresh)
        except Exception as exc:  # noqa: BLE001
            print(f"  - {name}: 写入失败 {exc}")
            continue
        total_new += created
        print(f"  - {name}: 现有 {len(existing)} → 新写 {created}，合计 {len(existing) + created}")

    for name, reason in skipped[:12]:
        print(f"  · 跳过 {name}（{reason}）")
    print(f"[完成] 本次新增 {total_new} 题")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
