#!/usr/bin/env python3
"""
项目优化初始化脚本：检查和配置题库、知识点、模块交互。

运行方式：
  python -m app.init_optimization

功能：
1. 验证题库规模和覆盖率
2. 检查知识点层级完整性
3. 验证模块间交互可用性
4. 输出优化报告
"""

import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.question_bank import BANKS, bank_of
from app.services.knowledge_hierarchy import (
    KNOWLEDGE_HIERARCHY,
    coverage_report,
    get_all_leaf_nodes,
)


def check_question_banks() -> dict:
    """检查题库规模。"""
    print("\n" + "=" * 80)
    print("【第一步】题库规模检查")
    print("=" * 80)
    
    total_banks = len(BANKS)
    total_questions = sum(len(bank.get("items", [])) for bank in BANKS)
    
    # 按模块分类
    modules = {}
    for bank in BANKS:
        module = bank.get("module", "未分类")
        if module not in modules:
            modules[module] = {"banks": 0, "questions": 0}
        modules[module]["banks"] += 1
        modules[module]["questions"] += len(bank.get("items", []))
    
    print(f"\n[OK] 总题库数：{total_banks}")
    print(f"✓ 总题数：{total_questions}")
    print("\n按模块分布：")
    for module, stats in sorted(modules.items()):
        print(f"  - {module:20s}: {stats['banks']:3d} 库, {stats['questions']:4d} 题")
    
    # 按考试科目统计
    science = {
        "英语": sum(
            len(bank.get("items", []))
            for bank in BANKS
            if bank.get("module", "").startswith(("听力", "阅读", "词汇", "语法", "翻译", "完形"))
        ),
        "数学": sum(
            len(bank.get("items", []))
            for bank in BANKS
            if bank.get("module", "").startswith(("高等数学", "线性代数", "概率论"))
        ),
    }
    
    print("\n按科目分布：")
    for subject, count in science.items():
        print(f"  - {subject:20s}: {count:4d} 题")
    
    return {
        "total_banks": total_banks,
        "total_questions": total_questions,
        "modules": modules,
        "by_subject": science,
        "status": "✓ PASS" if total_questions >= 300 else "✗ FAIL: 题库规模不足",
    }


def check_knowledge_hierarchy() -> dict:
    """检查知识点层级。"""
    print("\n" + "=" * 80)
    print("【第二步】知识点层级检查")
    print("=" * 80)
    
    leaf_nodes = get_all_leaf_nodes()
    coverage = coverage_report()
    
    print(f"\n✓ 总知识点数：{coverage['total_leaf_nodes']}")
    print(f"✓ 有题库覆盖的知识点：{coverage['covered']}")
    print(f"✓ 覆盖率：{coverage['coverage_rate']:.1f}%")
    
    print("\n按模块的覆盖情况：")
    for module, stats in coverage["by_module"].items():
        rate = stats["covered"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  - {module:20s}: {stats['covered']:2d}/{stats['total']:2d} ({rate:5.1f}%)")
    
    if coverage["uncovered_nodes"]:
        print(f"\n⚠ 未覆盖的知识点（{len(coverage['uncovered_nodes'])} 个）：")
        for node_id in coverage["uncovered_nodes"][:5]:  # 只显示前 5 个
            print(f"  - {node_id}")
        if len(coverage["uncovered_nodes"]) > 5:
            print(f"  ... 及其他 {len(coverage['uncovered_nodes']) - 5} 个")
    
    return {
        "total_nodes": coverage["total_leaf_nodes"],
        "covered": coverage["covered"],
        "coverage_rate": coverage["coverage_rate"],
        "uncovered_count": len(coverage["uncovered_nodes"]),
        "status": "✓ PASS" if coverage["coverage_rate"] >= 80 else "⚠ WARNING: 覆盖率不足 80%",
    }


def check_knowledge_point_matching() -> dict:
    """检查知识点与题库的匹配。"""
    print("\n" + "=" * 80)
    print("【第三步】知识点与题库匹配检查")
    print("=" * 80)
    
    sample_kps = [
        "高等数学", "函数与极限", "极限", "导数与微分", "导数", "积分",
        "线性代数", "矩阵", "行列式", "向量", "特征值", "二次型",
        "概率论与数理统计", "二项分布", "正态分布",
        "听力", "短对话", "阅读", "词汇", "语法",
    ]
    
    print("\n测试知识点匹配（采样）：")
    matches = 0
    misses = 0
    
    for kp_name in sample_kps:
        bank_info = bank_of(kp_name)
        status = "✓" if bank_info else "✗"
        matches += 1 if bank_info else 0
        misses += 0 if bank_info else 1
        source = bank_info.get("source", "未知") if bank_info else "无"
        size = bank_info.get("size", 0) if bank_info else 0
        print(f"  {status} {kp_name:20s} → {source:15s} ({size} 题)")
    
    match_rate = matches / len(sample_kps) * 100
    
    return {
        "sample_size": len(sample_kps),
        "matched": matches,
        "missed": misses,
        "match_rate": match_rate,
        "status": "✓ PASS" if match_rate >= 90 else "✗ FAIL: 匹配率过低",
    }


def check_module_integration() -> dict:
    """检查模块可用性。"""
    print("\n" + "=" * 80)
    print("【第四步】模块交互检查")
    print("=" * 80)
    
    modules_to_check = [
        ("quiz", "app.services.quiz", "quiz.py - 出题引擎"),
        ("mastery", "app.services.mastery_service", "mastery_service.py - 掌握度更新"),
        ("planner", "app.services.planner", "planner.py - 计划与重排"),
        ("diagnoser", "app.agents.diagnoser", "diagnoser.py - 错因诊断"),
        ("psychology", "app.services.psychology", "psychology.py - 学情诊断"),
        ("integration", "app.services.module_integration", "module_integration.py - 模块协调"),
    ]
    
    print("\n模块可用性检查：")
    all_ok = True
    
    for module_name, import_path, description in modules_to_check:
        try:
            __import__(import_path)
            status = "✓"
        except Exception as e:
            status = "✗"
            all_ok = False
            print(f"  {status} {module_name:15s} - {description}")
            print(f"     错误：{str(e)[:60]}")
            continue
        
        print(f"  {status} {module_name:15s} - {description}")
    
    return {
        "status": "✓ PASS" if all_ok else "✗ FAIL: 存在模块导入失败",
        "modules_checked": len(modules_to_check),
    }


def check_database_models() -> dict:
    """检查数据库模型。"""
    print("\n" + "=" * 80)
    print("【第五步】数据库模型检查")
    print("=" * 80)
    
    try:
        from app.models import (
            User, Goal, KnowledgePoint, Mastery, Task, Mistake,
            QuizAttempt, Report, MasteryHistory
        )
        
        models = [
            ("User", User, "用户模型"),
            ("Goal", Goal, "学习目标"),
            ("KnowledgePoint", KnowledgePoint, "知识点"),
            ("Mastery", Mastery, "掌握度"),
            ("Task", Task, "每日任务"),
            ("Mistake", Mistake, "错题记录"),
            ("QuizAttempt", QuizAttempt, "随堂测历史"),
            ("Report", Report, "周报"),
            ("MasteryHistory", MasteryHistory, "掌握度历史"),
        ]
        
        print("\n✓ 所有模型可用：")
        for name, model_class, description in models:
            print(f"  - {name:20s}: {description}")
        
        return {
            "status": "✓ PASS",
            "models_count": len(models),
        }
    except Exception as e:
        print(f"\n✗ 模型加载失败：{str(e)}")
        return {
            "status": "✗ FAIL",
            "error": str(e),
        }


def generate_report(results: dict) -> None:
    """生成优化检查报告。"""
    print("\n" + "=" * 80)
    print("【优化检查总结报告】")
    print("=" * 80)
    
    all_pass = all("PASS" in str(r.get("status", "")) for r in results.values())
    
    print("\n检查项目：")
    for step, result in results.items():
        status = result.get("status", "未知")
        icon = "✓" if "PASS" in status else "⚠" if "WARNING" in status else "✗"
        print(f"  {icon} {step}: {status}")
    
    print("\n" + "=" * 80)
    print("优化目标")
    print("=" * 80)
    print("""
    ✓ 第一阶段：题库系统完善
      - 题库规模：36 库 → 60 库（500+ 题）
      - 知识点细化：平面 → 树形（支持先修依赖）
      - 题库覆盖率 >= 90%
      
    ✓ 第二阶段：模块间交互优化
      - 出题 → 诊断 → 掌握度 → 重排 端到端流程
      - 学情诊断系统（疲劳、风险评估）
      - 数据导出与隐私保护
      
    ✓ 第三阶段：性能与可靠性
      - 缓存策略：Redis 7 天 TTL + 本地备份
      - 并发限流：防刷题、防滥用
      - 容错降级：4 层题源优先级
      
    ✓ 第四阶段：前端与 UX
      - 题库 UI 强化（题源、置信度、错因展示）
      - 知识点可视化（热力图、依赖关系）
      
    ✓ 第五阶段：部署与运维
      - Docker 多容器编排
      - CI/CD 流程自动化
    """)
    
    print("=" * 80)
    if all_pass:
        print("\n✓ 所有检查通过！项目优化已准备就绪。")
        print("\n后续步骤：")
        print("  1. 根据需求选择优化阶段启动")
        print("  2. 按优先级实现题库扩充、知识点细化")
        print("  3. 编写模块交互测试用例")
        print("  4. 进行端到端集成测试")
    else:
        print("\n⚠ 存在检查不通过项，请先修复问题。")
        print("\n问题排查：")
        for step, result in results.items():
            if "PASS" not in result.get("status", ""):
                print(f"  - {step}: {result.get('status', '未知')}")


def main():
    """主函数。"""
    print("\n" + "=" * 80)
    print("学迹项目优化初始化脚本")
    print("=" * 80)
    
    results = {
        "1. 题库规模": check_question_banks(),
        "2. 知识点层级": check_knowledge_hierarchy(),
        "3. 知识点匹配": check_knowledge_point_matching(),
        "4. 模块交互": check_module_integration(),
        "5. 数据库模型": check_database_models(),
    }
    
    generate_report(results)
    
    print("\n" + "=" * 80)
    print("检查完成！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
