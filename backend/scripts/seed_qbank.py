# -*- coding: utf-8 -*-
"""把内置题库播种到 tikuAdapter（课程名 = 知识点名），使出题链第一优先级真正对应。

- 幂等：tikuAdapter 按 (hash, course_name) 唯一索引去重，重复执行只补差量；
- 课程名取每个题库的 `points` 精确知识点名（与数据库知识点一一对应）；
- 重复题目（同一题挂到同 bank 的多个知识点）各课程独立存储，互不影响。
用法：cd backend && python scripts/seed_qbank.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import question_bank, tiku_bank  # noqa: E402


async def main() -> None:
    client = tiku_bank.get_client()
    if not tiku_bank.configured():
        print("tikuAdapter 未配置（TIKU_ADAPTER_URL），退出")
        return

    total_created = 0
    total_items = 0
    courses_reported = []
    for bank in question_bank.banks():
        items = bank.get("items") or []
        point_names = [p for p in (bank.get("points") or ()) if p]
        if not items or not point_names:
            continue
        total_items += len(items) * len(point_names)
        for point_name in point_names:
            payload = []
            for it in items:
                options = it.get("options") or []
                answer_index = it.get("answer_index")
                if answer_index is None or answer_index >= len(options):
                    continue
                payload.append(
                    {
                        "question": str(it.get("question") or "").strip(),
                        "type": 0,
                        "options": [str(o) for o in options],
                        "answer": [str(options[answer_index])],
                        "extra": str(it.get("explanation") or ""),
                        "course_name": point_name,
                    }
                )
            if not payload:
                continue
            created = await client.create(payload)
            total_created += created
            courses_reported.append((point_name, len(payload), created))

    print(f"内置题库题目×知识点共 {total_items} 条，本次新建 {total_created} 条（其余为已存在的重复，幂等跳过）")
    print("\n课程覆盖明细：")
    for name, count, created in courses_reported:
        print(f"  {name}: {count} 题（新建 {created}）")

    # 覆盖率验证
    names = sorted({name for name, _, _ in courses_reported})
    coverage = await tiku_bank.coverage(names)
    if coverage.get("status") == "ok":
        print(f"\n播种后覆盖率：{coverage['covered']}/{coverage['total']} "
              f"({coverage['rate']:.0%})")
        for name, info in coverage["points"].items():
            flag = "OK " if info["covered"] else "MISS"
            print(f"  [{flag}] {name}: {info['count']} 题")


if __name__ == "__main__":
    asyncio.run(main())
