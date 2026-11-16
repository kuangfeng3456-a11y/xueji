"""覆盖率统计脚本（环境无 coverage.py 时使用 stdlib trace 实现）。

用法（在 backend 目录执行）：
    python run_coverage.py
    python run_coverage.py -q -k planner

输出 backend/app 下每个文件的可执行行覆盖率，并以 80% 为门槛返回退出码。
"""

import sys
import threading
import trace as trace_module
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = (BASE_DIR / "app").resolve()
THRESHOLD = 80.0

_hits = {}
_inside_cache = {}


def _tracer(frame, event, arg):
    if event == "line":
        filename = frame.f_code.co_filename
        resolved = _inside_cache.get(filename)
        if resolved is None:
            try:
                resolved = str(Path(filename).resolve())
            except (OSError, ValueError):
                resolved = ""
            _inside_cache[filename] = resolved
        if resolved.startswith(str(APP_DIR)):
            _hits.setdefault(resolved, set()).add(frame.f_lineno)
    return _tracer


def _collect():
    rows = []
    total_hit = 0
    total_exec = 0
    for file in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        executable = set(trace_module._find_executable_linenos(str(file)))
        if not executable:
            continue
        hit = _hits.get(str(file), set()) & executable
        total_hit += len(hit)
        total_exec += len(executable)
        rows.append(
            {
                "file": str(file.relative_to(BASE_DIR)).replace("\\", "/"),
                "hit": len(hit),
                "total": len(executable),
                "pct": round(len(hit) / len(executable) * 100, 2),
            }
        )
    return rows, total_hit, total_exec


def main() -> int:
    args = sys.argv[1:] or ["-q"]
    sys.settrace(_tracer)
    # FastAPI 的同步路由在线程池中执行，必须同时设置线程级 tracer
    threading.settrace(_tracer)
    try:
        exit_code = pytest.main([str(BASE_DIR / "tests")] + args)
    finally:
        sys.settrace(None)
        threading.settrace(None)

    rows, total_hit, total_exec = _collect()
    overall = round(total_hit / total_exec * 100, 2) if total_exec else 0.0

    print()
    print("=" * 66)
    print("覆盖率报告（stdlib trace，行覆盖）")
    print("=" * 66)
    print(f"{'文件':<44}{'命中':>8}{'可执行':>8}{'覆盖率':>9}")
    print("-" * 66)
    for row in sorted(rows, key=lambda item: item["pct"]):
        print(f"{row['file']:<44}{row['hit']:>8}{row['total']:>8}{row['pct']:>8.2f}%")
    print("-" * 66)
    print(f"{'合计':<44}{total_hit:>8}{total_exec:>8}{overall:>8.2f}%")
    print(f"门槛 {THRESHOLD}% => {'通过' if overall >= THRESHOLD else '未通过'}")
    print("=" * 66)

    if exit_code != 0:
        return int(exit_code)
    return 0 if overall >= THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())