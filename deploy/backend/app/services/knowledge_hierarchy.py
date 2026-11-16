"""
知识点层级化配置：从平面列表转为树形结构。

新架构支持：
- 一级模块（如「高等数学」）
- 二级知识点（如「导数与微分」）
- 三级微知识点（如「导数应用：单调性」）

便于：
1. 精确知识点检索（避免「极限」混淆）
2. 先修依赖追溯（导数依赖极限）
3. 掌握度聚合（微知识点 → 知识点 → 模块）
4. 题库覆盖统计
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

@dataclass
class KnowledgePointNode:
    """知识点树节点。"""
    id: str  # 全局唯一标识，如 "math_calculus_derivative_monotone"
    name: str  # 显示名称，如 "导数应用：单调性"
    module: str  # 所属模块，如 "高等数学"
    level: int  # 层级：1（模块）、2（知识点）、3（微知识点）
    weight: float  # 权重，用于优先级计算（0-1）
    parents: List[str]  # 上级节点 ID 列表（支持多继承）
    children: List[str]  # 下级节点 ID 列表
    qbank_key: Optional[str]  # 对应的题库 key（仅叶子节点）
    prerequisites: List[str]  # 先修知识点 ID（如 limit_function 是 derivative 的前置）
    description: str  # 详细描述
    mastery_aggregate_method: str  # 掌握度聚合方法："avg"（平均）/ "min"（最低）/ "weighted"（加权）

# ============================================================================
# 高等数学知识点树
# ============================================================================
ADVANCED_MATH_HIERARCHY: Dict[str, KnowledgePointNode] = {
    # 一级模块
    "math_advanced": KnowledgePointNode(
        id="math_advanced",
        name="高等数学",
        module="高等数学",
        level=1,
        weight=1.0,
        parents=[],
        children=["math_function_limits", "math_derivatives", "math_integrals", "math_series_ode"],
        qbank_key=None,
        prerequisites=[],
        description="包含函数、极限、导数、积分、级数、微分方程等内容",
        mastery_aggregate_method="weighted",
    ),
    # 二级：函数与极限
    "math_function_limits": KnowledgePointNode(
        id="math_function_limits",
        name="函数与极限",
        module="高等数学",
        level=2,
        weight=0.9,
        parents=["math_advanced"],
        children=["math_function_properties", "math_limit_concept", "math_continuity"],
        qbank_key=None,
        prerequisites=[],
        description="函数基础、极限、连续性",
        mastery_aggregate_method="weighted",
    ),
    # 三级微知识点
    "math_function_properties": KnowledgePointNode(
        id="math_function_properties",
        name="函数性质",
        module="高等数学",
        level=3,
        weight=0.7,
        parents=["math_function_limits"],
        children=[],
        qbank_key="function_properties",  # 对应题库
        prerequisites=[],
        description="函数的奇偶性、单调性、周期性、有界性",
        mastery_aggregate_method="avg",
    ),
    "math_limit_concept": KnowledgePointNode(
        id="math_limit_concept",
        name="极限概念",
        module="高等数学",
        level=3,
        weight=0.8,
        parents=["math_function_limits"],
        children=[],
        qbank_key="limits",
        prerequisites=[],
        description="数列极限、函数极限、无穷小与无穷大",
        mastery_aggregate_method="avg",
    ),
    # 二级：导数与微分
    "math_derivatives": KnowledgePointNode(
        id="math_derivatives",
        name="导数与微分",
        module="高等数学",
        level=2,
        weight=0.95,
        parents=["math_advanced"],
        children=["math_derivative_basic", "math_derivative_application"],
        qbank_key=None,
        prerequisites=["math_limit_concept"],
        description="导数定义、求导法则、微分应用",
        mastery_aggregate_method="weighted",
    ),
    "math_derivative_basic": KnowledgePointNode(
        id="math_derivative_basic",
        name="导数与求导",
        module="高等数学",
        level=3,
        weight=0.8,
        parents=["math_derivatives"],
        children=[],
        qbank_key="derivative",
        prerequisites=["math_limit_concept"],
        description="导数定义、基本导数公式、求导法则",
        mastery_aggregate_method="avg",
    ),
    "math_derivative_application": KnowledgePointNode(
        id="math_derivative_application",
        name="导数应用",
        module="高等数学",
        level=3,
        weight=0.9,
        parents=["math_derivatives"],
        children=["math_derivative_monotone", "math_derivative_extreme"],
        qbank_key=None,
        prerequisites=["math_derivative_basic"],
        description="单调性、极值、凹凸性、方程应用",
        mastery_aggregate_method="weighted",
    ),
    # 三级细化
    "math_derivative_monotone": KnowledgePointNode(
        id="math_derivative_monotone",
        name="导数应用：单调性",
        module="高等数学",
        level=3,
        weight=0.85,
        parents=["math_derivative_application"],
        children=[],
        qbank_key="derivative_application_monotone",
        prerequisites=["math_derivative_basic"],
        description="用导数判断函数单调性、求单调区间",
        mastery_aggregate_method="avg",
    ),
    "math_derivative_extreme": KnowledgePointNode(
        id="math_derivative_extreme",
        name="导数应用：极值",
        module="高等数学",
        level=3,
        weight=0.85,
        parents=["math_derivative_application"],
        children=[],
        qbank_key="derivative_application_extreme",
        prerequisites=["math_derivative_basic"],
        description="极值、最值、二阶导数判别法",
        mastery_aggregate_method="avg",
    ),
    # 二级：积分
    "math_integrals": KnowledgePointNode(
        id="math_integrals",
        name="积分学",
        module="高等数学",
        level=2,
        weight=0.95,
        parents=["math_advanced"],
        children=["math_indefinite_integral", "math_definite_integral"],
        qbank_key=None,
        prerequisites=["math_derivative_basic"],
        description="不定积分、定积分、应用",
        mastery_aggregate_method="weighted",
    ),
    "math_indefinite_integral": KnowledgePointNode(
        id="math_indefinite_integral",
        name="不定积分",
        module="高等数学",
        level=3,
        weight=0.8,
        parents=["math_integrals"],
        children=[],
        qbank_key="indefinite_integral",
        prerequisites=["math_derivative_basic"],
        description="原函数、基本积分公式、分部积分",
        mastery_aggregate_method="avg",
    ),
    "math_definite_integral": KnowledgePointNode(
        id="math_definite_integral",
        name="定积分",
        module="高等数学",
        level=3,
        weight=0.85,
        parents=["math_integrals"],
        children=[],
        qbank_key="definite_integral",
        prerequisites=["math_indefinite_integral"],
        description="定积分定义、性质、计算、几何应用",
        mastery_aggregate_method="avg",
    ),
    # 二级：级数与微分方程
    "math_series_ode": KnowledgePointNode(
        id="math_series_ode",
        name="级数与微分方程",
        module="高等数学",
        level=2,
        weight=0.85,
        parents=["math_advanced"],
        children=["math_series", "math_ode"],
        qbank_key=None,
        prerequisites=["math_definite_integral"],
        description="无穷级数、幂级数、微分方程",
        mastery_aggregate_method="weighted",
    ),
    "math_series": KnowledgePointNode(
        id="math_series",
        name="无穷级数",
        module="高等数学",
        level=3,
        weight=0.7,
        parents=["math_series_ode"],
        children=[],
        qbank_key="series",
        prerequisites=["math_limit_concept"],
        description="级数敛散性、幂级数、泰勒级数",
        mastery_aggregate_method="avg",
    ),
    "math_ode": KnowledgePointNode(
        id="math_ode",
        name="常微分方程",
        module="高等数学",
        level=3,
        weight=0.75,
        parents=["math_series_ode"],
        children=[],
        qbank_key="ode_linear_first",
        prerequisites=["math_definite_integral"],
        description="一阶线性ODE、齐次方程、变系数方程",
        mastery_aggregate_method="avg",
    ),
}

# ============================================================================
# 线性代数知识点树
# ============================================================================
LINEAR_ALGEBRA_HIERARCHY: Dict[str, KnowledgePointNode] = {
    "math_linear_algebra": KnowledgePointNode(
        id="math_linear_algebra",
        name="线性代数",
        module="线性代数",
        level=1,
        weight=0.9,
        parents=[],
        children=["math_vector_space", "math_matrix_theory", "math_eigenvalue_quadratic"],
        qbank_key=None,
        prerequisites=[],
        description="向量、矩阵、线性变换、特征值、二次型",
        mastery_aggregate_method="weighted",
    ),
    # 二级：向量空间
    "math_vector_space": KnowledgePointNode(
        id="math_vector_space",
        name="向量与向量空间",
        module="线性代数",
        level=2,
        weight=0.85,
        parents=["math_linear_algebra"],
        children=["math_vector", "math_rank"],
        qbank_key=None,
        prerequisites=[],
        description="向量、线性相关、向量空间、秩",
        mastery_aggregate_method="weighted",
    ),
    "math_vector": KnowledgePointNode(
        id="math_vector",
        name="向量与线性相关性",
        module="线性代数",
        level=3,
        weight=0.8,
        parents=["math_vector_space"],
        children=[],
        qbank_key="vector",
        prerequisites=[],
        description="向量运算、线性相关、线性无关、向量组秩",
        mastery_aggregate_method="avg",
    ),
    "math_rank": KnowledgePointNode(
        id="math_rank",
        name="矩阵的秩",
        module="线性代数",
        level=3,
        weight=0.75,
        parents=["math_vector_space"],
        children=[],
        qbank_key="rank",
        prerequisites=["math_vector"],
        description="秩的定义、计算、性质、应用",
        mastery_aggregate_method="avg",
    ),
    # 二级：矩阵论
    "math_matrix_theory": KnowledgePointNode(
        id="math_matrix_theory",
        name="矩阵论",
        module="线性代数",
        level=2,
        weight=0.9,
        parents=["math_linear_algebra"],
        children=["math_matrix", "math_determinant", "math_similar_matrix"],
        qbank_key=None,
        prerequisites=["math_rank"],
        description="矩阵、行列式、初等变换、相似矩阵",
        mastery_aggregate_method="weighted",
    ),
    "math_matrix": KnowledgePointNode(
        id="math_matrix",
        name="矩阵",
        module="线性代数",
        level=3,
        weight=0.8,
        parents=["math_matrix_theory"],
        children=[],
        qbank_key="matrix",
        prerequisites=[],
        description="矩阵运算、逆矩阵、初等变换",
        mastery_aggregate_method="avg",
    ),
    "math_determinant": KnowledgePointNode(
        id="math_determinant",
        name="行列式",
        module="线性代数",
        level=3,
        weight=0.75,
        parents=["math_matrix_theory"],
        children=[],
        qbank_key="determinant",
        prerequisites=["math_rank"],
        description="行列式定义、计算、Cramer 法则",
        mastery_aggregate_method="avg",
    ),
    "math_similar_matrix": KnowledgePointNode(
        id="math_similar_matrix",
        name="相似矩阵与对角化",
        module="线性代数",
        level=3,
        weight=0.7,
        parents=["math_matrix_theory"],
        children=[],
        qbank_key="similar_matrix",
        prerequisites=["math_matrix"],
        description="相似关系、对角化、Jordan 标准形",
        mastery_aggregate_method="avg",
    ),
    # 二级：特征值与二次型
    "math_eigenvalue_quadratic": KnowledgePointNode(
        id="math_eigenvalue_quadratic",
        name="特征值与二次型",
        module="线性代数",
        level=2,
        weight=0.85,
        parents=["math_linear_algebra"],
        children=["math_eigenvalue", "math_quadratic_form"],
        qbank_key=None,
        prerequisites=["math_determinant"],
        description="特征值、特征向量、二次型、正定性",
        mastery_aggregate_method="weighted",
    ),
    "math_eigenvalue": KnowledgePointNode(
        id="math_eigenvalue",
        name="特征值与特征向量",
        module="线性代数",
        level=3,
        weight=0.8,
        parents=["math_eigenvalue_quadratic"],
        children=[],
        qbank_key="eigen_quadratic",
        prerequisites=["math_determinant", "math_vector"],
        description="特征多项式、特征值、特征向量、Cayley-Hamilton",
        mastery_aggregate_method="avg",
    ),
    "math_quadratic_form": KnowledgePointNode(
        id="math_quadratic_form",
        name="二次型",
        module="线性代数",
        level=3,
        weight=0.7,
        parents=["math_eigenvalue_quadratic"],
        children=[],
        qbank_key="quadratic_form",
        prerequisites=["math_eigenvalue"],
        description="二次型矩阵、标准化、正定二次型、Sylvester定理",
        mastery_aggregate_method="avg",
    ),
}

# ============================================================================
# 概率论与数理统计知识点树
# ============================================================================
PROBABILITY_HIERARCHY: Dict[str, KnowledgePointNode] = {
    "math_probability_statistics": KnowledgePointNode(
        id="math_probability_statistics",
        name="概率论与数理统计",
        module="概率论与数理统计",
        level=1,
        weight=0.85,
        parents=[],
        children=["math_probability_foundation", "math_distribution", "math_statistics"],
        qbank_key=None,
        prerequisites=[],
        description="概率基础、随机变量、分布、参数估计、假设检验",
        mastery_aggregate_method="weighted",
    ),
    # 二级：概率基础
    "math_probability_foundation": KnowledgePointNode(
        id="math_probability_foundation",
        name="概率基础",
        module="概率论与数理统计",
        level=2,
        weight=0.75,
        parents=["math_probability_statistics"],
        children=["math_event_probability", "math_conditional_probability"],
        qbank_key=None,
        prerequisites=[],
        description="事件、概率定义、条件概率、独立性",
        mastery_aggregate_method="weighted",
    ),
    "math_event_probability": KnowledgePointNode(
        id="math_event_probability",
        name="事件与概率",
        module="概率论与数理统计",
        level=3,
        weight=0.7,
        parents=["math_probability_foundation"],
        children=[],
        qbank_key="probability",
        prerequisites=[],
        description="样本空间、事件、概率定义、概率性质",
        mastery_aggregate_method="avg",
    ),
    # 二级：随机变量与分布
    "math_distribution": KnowledgePointNode(
        id="math_distribution",
        name="随机变量与分布",
        module="概率论与数理统计",
        level=2,
        weight=0.9,
        parents=["math_probability_statistics"],
        children=["math_discrete_distribution", "math_continuous_distribution", "math_joint_distribution"],
        qbank_key=None,
        prerequisites=["math_event_probability"],
        description="随机变量、分布函数、离散与连续分布",
        mastery_aggregate_method="weighted",
    ),
    "math_discrete_distribution": KnowledgePointNode(
        id="math_discrete_distribution",
        name="离散分布",
        module="概率论与数理统计",
        level=3,
        weight=0.8,
        parents=["math_distribution"],
        children=[],
        qbank_key="discrete_distribution",
        prerequisites=["math_event_probability"],
        description="二项分布、泊松分布、几何分布、超几何分布",
        mastery_aggregate_method="avg",
    ),
    "math_continuous_distribution": KnowledgePointNode(
        id="math_continuous_distribution",
        name="连续分布",
        module="概率论与数理统计",
        level=3,
        weight=0.85,
        parents=["math_distribution"],
        children=[],
        qbank_key="continuous_distribution",
        prerequisites=["math_event_probability"],
        description="均匀分布、指数分布、正态分布、卡方分布、t分布",
        mastery_aggregate_method="avg",
    ),
    # 二级：数理统计
    "math_statistics": KnowledgePointNode(
        id="math_statistics",
        name="数理统计",
        module="概率论与数理统计",
        level=2,
        weight=0.8,
        parents=["math_probability_statistics"],
        children=["math_estimation", "math_hypothesis_testing"],
        qbank_key=None,
        prerequisites=["math_discrete_distribution", "math_continuous_distribution"],
        description="参数估计、假设检验、置信区间",
        mastery_aggregate_method="weighted",
    ),
    "math_estimation": KnowledgePointNode(
        id="math_estimation",
        name="参数估计",
        module="概率论与数理统计",
        level=3,
        weight=0.75,
        parents=["math_statistics"],
        children=[],
        qbank_key="parameter_estimation",
        prerequisites=["math_discrete_distribution"],
        description="点估计、矩估计、最大似然估计、置信区间",
        mastery_aggregate_method="avg",
    ),
    "math_hypothesis_testing": KnowledgePointNode(
        id="math_hypothesis_testing",
        name="假设检验",
        module="概率论与数理统计",
        level=3,
        weight=0.8,
        parents=["math_statistics"],
        children=[],
        qbank_key="hypothesis_testing",
        prerequisites=["math_continuous_distribution"],
        description="显著性检验、第一第二类错误、p值、各种检验方法",
        mastery_aggregate_method="avg",
    ),
}

# ============================================================================
# 全局层级树
# ============================================================================
KNOWLEDGE_HIERARCHY: Dict[str, KnowledgePointNode] = {
    **ADVANCED_MATH_HIERARCHY,
    **LINEAR_ALGEBRA_HIERARCHY,
    **PROBABILITY_HIERARCHY,
}


def get_node_by_id(node_id: str) -> Optional[KnowledgePointNode]:
    """按 ID 获取知识点节点。"""
    return KNOWLEDGE_HIERARCHY.get(node_id)


def get_all_leaf_nodes() -> List[KnowledgePointNode]:
    """获取所有叶子节点（对应题库的微知识点）。"""
    return [node for node in KNOWLEDGE_HIERARCHY.values() if node.level == 3 and node.qbank_key]


def get_children(node_id: str) -> List[KnowledgePointNode]:
    """获取节点的所有直接子节点。"""
    node = get_node_by_id(node_id)
    if not node:
        return []
    return [get_node_by_id(cid) for cid in node.children if get_node_by_id(cid)]


def get_ancestors(node_id: str) -> List[KnowledgePointNode]:
    """获取节点的所有祖先（上级）。"""
    node = get_node_by_id(node_id)
    if not node:
        return []
    ancestors = []
    for pid in node.parents:
        parent = get_node_by_id(pid)
        if parent:
            ancestors.append(parent)
            ancestors.extend(get_ancestors(pid))
    return ancestors


def get_prerequisites(node_id: str) -> List[KnowledgePointNode]:
    """获取先修知识点。"""
    node = get_node_by_id(node_id)
    if not node:
        return []
    prereq_nodes = [get_node_by_id(pid) for pid in node.prerequisites if get_node_by_id(pid)]
    return [n for n in prereq_nodes if n]


def get_by_module(module: str) -> List[KnowledgePointNode]:
    """按模块获取所有知识点。"""
    return [node for node in KNOWLEDGE_HIERARCHY.values() if node.module == module]


def coverage_report() -> Dict:
    """生成题库覆盖率报告。"""
    leaf_nodes = get_all_leaf_nodes()
    total = len(leaf_nodes)
    covered = len([n for n in leaf_nodes if n.qbank_key])
    uncovered = [n for n in leaf_nodes if not n.qbank_key]
    
    return {
        "total_leaf_nodes": total,
        "covered": covered,
        "coverage_rate": covered / total * 100 if total > 0 else 0,
        "uncovered_nodes": [n.id for n in uncovered],
        "by_module": {
            module: {
                "total": len(get_by_module(module)),
                "covered": len([n for n in get_by_module(module) if n.level == 3 and n.qbank_key]),
            }
            for module in ["高等数学", "线性代数", "概率论与数理统计"]
        },
    }
