#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目优化检查脚本（简化版）

运行方式：python check_optimization.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.question_bank import BANKS
from app.services.knowledge_hierarchy import get_all_leaf_nodes


def main():
    print("=" * 80)
    print("XUEJI PROJECT OPTIMIZATION CHECK")
    print("=" * 80)
    
    # 1. Check question banks
    print("\n[STEP 1] Question Bank Statistics")
    print("-" * 80)
    
    total_banks = len(BANKS)
    total_questions = sum(len(bank.get("items", [])) for bank in BANKS)
    
    print(f"Total banks: {total_banks}")
    print(f"Total questions: {total_questions}")
    
    # Group by module
    modules = {}
    for bank in BANKS:
        module = bank.get("module", "Unknown")
        if module not in modules:
            modules[module] = {"banks": 0, "questions": 0}
        modules[module]["banks"] += 1
        modules[module]["questions"] += len(bank.get("items", []))
    
    print("\nBy module:")
    for module, stats in sorted(modules.items()):
        print(f"  {module:30s}: {stats['banks']:3d} banks, {stats['questions']:4d} questions")
    
    if total_questions < 300:
        print(f"\n[WARNING] Question count {total_questions} < 300 (target)")
    else:
        print(f"\n[OK] Question count {total_questions} >= 300")
    
    # 2. Check knowledge point hierarchy
    print("\n[STEP 2] Knowledge Point Hierarchy")
    print("-" * 80)
    
    leaf_nodes = get_all_leaf_nodes()
    print(f"Total leaf nodes: {len(leaf_nodes)}")
    
    covered = len([n for n in leaf_nodes if n.qbank_key])
    coverage_rate = (covered / len(leaf_nodes) * 100) if leaf_nodes else 0
    
    print(f"Covered by question banks: {covered}/{len(leaf_nodes)}")
    print(f"Coverage rate: {coverage_rate:.1f}%")
    
    if coverage_rate < 80:
        print(f"\n[WARNING] Coverage rate {coverage_rate:.1f}% < 80% (target)")
    else:
        print(f"\n[OK] Coverage rate {coverage_rate:.1f}% >= 80%")
    
    # 3. Module integration check
    print("\n[STEP 3] Module Integration")
    print("-" * 80)
    
    modules_to_check = {
        "quiz": "app.services.quiz",
        "mastery": "app.services.mastery_service",
        "planner": "app.services.planner",
        "diagnoser": "app.agents.diagnoser",
        "integration": "app.services.module_integration",
    }
    
    all_ok = True
    for name, import_path in modules_to_check.items():
        try:
            __import__(import_path)
            print(f"  [OK] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {str(e)[:50]}")
            all_ok = False
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    checks = [
        ("Question banks", total_questions >= 300),
        ("Knowledge hierarchy", coverage_rate >= 80),
        ("Module integration", all_ok),
    ]
    
    passed = sum(1 for _, result in checks if result)
    
    for name, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  {name:30s}: {status}")
    
    print(f"\nTotal: {passed}/{len(checks)} checks passed")
    
    if passed == len(checks):
        print("\n[OK] All optimization checks passed!")
    else:
        print(f"\n[WARNING] {len(checks) - passed} checks failed")
    
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
