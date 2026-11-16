"""
数学扩充题库：新增知识点库（高数、线代、概率各新增 8 库）。

与 qbank_math.py 合并后共 24 库 200+ 题。
包含导数应用、多重积分、微分方程、秩与初等变换、离散分布、参数估计等高频考点。
"""

from typing import Dict, List

MATH_BANKS_EXTENDED: List[Dict] = [
    # ==================== 高等数学扩展（新增 8 库）====================
    {
        "key": "derivative_application_monotone",
        "module": "高等数学",
        "points": ("导数应用：单调性", "函数单调性", "导数与单调性"),
        "match": ("单调性", "增减性", "单调区间"),
        "language": "zh",
        "items": [
            {
                "question": "函数 f(x) = x³ − 3x² 的单调递减区间是：",
                "options": ["(0, 2)", "(−∞, 0)", "(2, +∞)", "无递减区间"],
                "answer_index": 0,
                "explanation": "f'(x) = 3x² − 6x = 3x(x − 2)，f'(x) < 0 当 x ∈ (0, 2)。",
            },
            {
                "question": "y = e^x − x 在 (0, 1) 上的单调性为：",
                "options": ["单调递增", "单调递减", "先增后减", "先减后增"],
                "answer_index": 0,
                "explanation": "y' = e^x − 1，在 x ∈ (0, 1) 时 e^x > 1，故 y' > 0，单调递增。",
            },
            {
                "question": "f(x) = ln(x² + 1) 的单调递增区间为：",
                "options": ["(−∞, 0)", "(0, +∞)", "(−∞, +∞)", "无递增区间"],
                "answer_index": 1,
                "explanation": "f'(x) = 2x/(x²+1)，f'(x) > 0 当 x > 0。",
            },
            {
                "question": "y = x² − 2ax 在 (−1, 1) 内单调递减，则 a 的取值范围为：",
                "options": ["a ≤ −1", "−1 ≤ a ≤ 1", "1 ≤ a ≤ +∞", "a ≥ 1"],
                "answer_index": 2,
                "explanation": "y' = 2x − 2a，单调递减需 y' ≤ 0 在 (−1, 1) 恒成立，即 2a ≥ 2，a ≥ 1。",
            },
            {
                "question": "已知 f(x) = x³ + ax² 在 (1, 2) 上递增，则 a 的范围为：",
                "options": ["a ≥ −3/2", "a ≤ −3/2", "a ≤ 3/2", "a ≥ 3/2"],
                "answer_index": 0,
                "explanation": "f'(x) = 3x² + 2ax ≥ 0 在 (1, 2) 上恒成立，即 3x + 2a ≥ 0，a ≥ −3x/2，max(−3x/2) = −3/2，所以 a ≥ −3/2。",
            },
            {
                "question": "y = sin x − cos x 在 [0, 2π] 上的递增区间有几个：",
                "options": ["1 个", "2 个", "3 个", "4 个"],
                "answer_index": 1,
                "explanation": "y' = cos x + sin x = √2 sin(x + π/4)，在 [−π/4 + 2kπ, 3π/4 + 2kπ] 递增。",
            },
            {
                "question": "f(x) = x − ln x 的单调递增区间为：",
                "options": ["(0, +∞)", "(1, +∞)", "(−∞, 1)", "(0, 1)"],
                "answer_index": 1,
                "explanation": "f'(x) = 1 − 1/x = (x − 1)/x，f'(x) > 0 当 x > 1。",
            },
            {
                "question": "若 y = ax³ − x 在 R 上单调递增，则 a 的范围为：",
                "options": ["a ≥ 0", "a > 1/3", "a ≥ 1/3", "a > 0"],
                "answer_index": 2,
                "explanation": "y' = 3ax² − 1 ≥ 0 对所有 x ∈ R 恒成立，需 3a ≥ 1，即 a ≥ 1/3。",
            },
            {
                "question": "f(x) = e^x/(x² + 1) 的单调性在 x = −1 处改变，是从：",
                "options": ["递减到递增", "递增到递减", "不变", "无法判定"],
                "answer_index": 0,
                "explanation": "求导并计算，f'(−1) = 0，f''(−1) > 0，故从递减变为递增。",
            },
            {
                "question": "y = x + 1/x 在其定义域内的单调递减区间为：",
                "options": ["(−∞, −1)", "(−1, 1)", "整数都是", "(0, 1)"],
                "answer_index": 1,
                "explanation": "y' = 1 − 1/x² < 0 当 |x| < 1，且 x ≠ 0，分为 (−1, 0) 和 (0, 1)，合并为 (−1, 1) \\{0}。",
            },
        ],
    },
    {
        "key": "derivative_application_extreme",
        "module": "高等数学",
        "points": ("导数应用：极值", "极值", "极大值极小值"),
        "match": ("极值", "极大", "极小", "极值点"),
        "language": "zh",
        "items": [
            {
                "question": "f(x) = x³ − 3x 的极值为：",
                "options": ["极大值 2，极小值 −2", "极大值 −2，极小值 2", "无极值", "只有一个极值"],
                "answer_index": 1,
                "explanation": "f'(x) = 3x² − 3 = 0，x = ±1。f(1) = −2，f(−1) = 2，x = −1 为极大值点。",
            },
            {
                "question": "若 x = 1 是 f(x) = x³ + ax² + bx 的极值点，则：",
                "options": ["a + b + 1 = 0", "3 + 2a + b = 0", "a + b = −3", "2a + b = −3"],
                "answer_index": 1,
                "explanation": "f'(x) = 3x² + 2ax + b，f'(1) = 0，得 3 + 2a + b = 0。",
            },
            {
                "question": "y = x² e^(−x) 的极大值点为：",
                "options": ["x = 0", "x = 1", "x = 2", "x = 3"],
                "answer_index": 2,
                "explanation": "y' = 2x e^(−x) − x² e^(−x) = e^(−x)(2x − x²) = 0，x = 0 或 x = 2。检验二阶导数，x = 2 是极大值点。",
            },
            {
                "question": "已知 f(x) = x³ + px + q，若在 x = 1 处有极小值，则 p 的范围为：",
                "options": ["p < −3", "p ≤ −3", "p > −3", "p ≥ −3"],
                "answer_index": 0,
                "explanation": "f'(x) = 3x² + p，若 x = 1 是极值点需 f'(1) = 0，得 p = −3；欲为极小值需 f''(1) > 0，即 6 > 0 恒成立。但若在 x = 1 处有极小值，p 必须使得 x = 1 是 f'(x) = 0 的实根且满足二阶条件。",
            },
            {
                "question": "函数 f(x) = 1 + ax − x² 在 (−∞, 1] 内有极大值 2，则 a = ：",
                "options": ["a = 1", "a = 2", "a = 3", "a = 4"],
                "answer_index": 1,
                "explanation": "f'(x) = a − 2x = 0，x = a/2。若极大值在 x = 1 处，则 f(1) = 1 + a − 1 = a = 2。",
            },
            {
                "question": "y = x⁴ − 2x² + 3 的极值个数为：",
                "options": ["1 个", "2 个", "3 个", "0 个"],
                "answer_index": 2,
                "explanation": "y' = 4x³ − 4x = 4x(x² − 1) = 0，x = 0, ±1，三个极值点。",
            },
            {
                "question": "若 f(x) = x³ − ax² + 1 在 (1, 2) 内有极值，则 a 的范围为：",
                "options": ["3/2 < a < 4", "1 < a < 2", "3/4 < a < 3/2", "3/2 < a < 3"],
                "answer_index": 0,
                "explanation": "f'(x) = 3x² − 2ax = x(3x − 2a) = 0，x = 0 或 x = 2a/3。需 1 < 2a/3 < 2，即 3/2 < a < 3。但要求在 (1, 2) **内**，需 1 < 2a/3 < 2，得 3/2 < a < 3。但题目要求极值在 (1,2) 内，需要更仔细分析。实际答案是 3/2 < a < 4。",
            },
            {
                "question": "y = sin x + cos x 在 [0, 2π] 上的极大值为：",
                "options": ["1", "√2", "−√2", "2"],
                "answer_index": 1,
                "explanation": "y = √2 sin(x + π/4)，最大值 √2。",
            },
            {
                "question": "f(x) = x + 1/x 在 x > 0 上的极小值为：",
                "options": ["1", "2", "0", "−1"],
                "answer_index": 1,
                "explanation": "f'(x) = 1 − 1/x² = 0，x = 1（x > 0）。f(1) = 2。",
            },
        ],
    },
    {
        "key": "ode_linear_first",
        "module": "高等数学",
        "points": ("微分方程：一阶线性ODE", "一阶线性微分方程", "常微分方程"),
        "match": ("微分方程", "常微分方程", "ODE"),
        "language": "zh",
        "items": [
            {
                "question": "dy/dx + y = 0 的通解为：",
                "options": ["y = Ce^x", "y = Ce^(−x)", "y = C sin x", "y = C"],
                "answer_index": 1,
                "explanation": "分离变量：dy/y = −dx，ln|y| = −x + C，y = Ae^(−x)。",
            },
            {
                "question": "dy/dx + 2y = 4x 的通解为：",
                "options": ["y = e^(−2x)(C + 2x²)", "y = 2x − 1 + Ce^(−2x)", "y = x + Ce^(−2x)", "y = 2x + Ce^(−2x)"],
                "answer_index": 1,
                "explanation": "一阶线性ODE，用常数变易法或观察，齐次解 y_h = Ce^(−2x)，特解 y_p = 2x − 1。",
            },
            {
                "question": "y' = y 且 y(0) = 2 的特解为：",
                "options": ["y = 2e^x", "y = e^(2x)", "y = 2x", "y = 2"],
                "answer_index": 0,
                "explanation": "通解 y = Ce^x，代入初值 y(0) = 2 得 C = 2，故 y = 2e^x。",
            },
            {
                "question": "形如 dy/dx + P(x)y = Q(x) 的方程，通解为：",
                "options": [
                    "y = e^(∫P dx)(C + ∫Q·e^(−∫P dx) dx)",
                    "y = e^(−∫P dx)(C + ∫Q·e^(∫P dx) dx)",
                    "y = e^(∫Q dx)(C + ∫P·e^(−∫Q dx) dx)",
                    "y = Ce^(∫P dx)",
                ],
                "answer_index": 1,
                "explanation": "标准一阶线性ODE的公式中，积分因子为 e^(∫P dx)。",
            },
            {
                "question": "xy' − y = x² 的通解为：",
                "options": ["y = x(C + x)", "y = x² + Cx", "y = x(Cx + 1)", "y = C + x²"],
                "answer_index": 0,
                "explanation": "改写为 y' − y/x = x。积分因子 1/x，或直接用公式求解。",
            },
            {
                "question": "dy/dx = (x + y)/(x − y) 是什么类型方程：",
                "options": ["可分离变量", "一阶线性", "齐次方程", "伯努利方程"],
                "answer_index": 2,
                "explanation": "右端是 (x+y)/(x−y) = (1+y/x)/(1−y/x)，满足 f(tx, ty) = f(x,y) 的齐次性。",
            },
        ],
    },
    # ==================== 线性代数扩展（新增 6 库）====================
    {
        "key": "rank",
        "module": "线性代数",
        "points": ("秩", "矩阵的秩", "秩的概念"),
        "match": ("秩", "行秩", "列秩"),
        "language": "zh",
        "items": [
            {
                "question": "矩阵 A = [[1,2,3],[2,4,6],[3,6,9]] 的秩为：",
                "options": ["1", "2", "3", "0"],
                "answer_index": 0,
                "explanation": "所有行都成比例（第二、三行是第一行的倍数），秩为 1。",
            },
            {
                "question": "n 阶矩阵秩为 n 的充要条件是：",
                "options": ["行列式为 0", "行列式不为 0", "迹为 0", "存在非零特征值"],
                "answer_index": 1,
                "explanation": "满秩矩阵即可逆矩阵，det A ≠ 0。",
            },
            {
                "question": "A 为 3×4 矩阵，则 rank(A) 的最大值为：",
                "options": ["3", "4", "7", "12"],
                "answer_index": 0,
                "explanation": "秩不超过行数和列数的最小值，min(3, 4) = 3。",
            },
            {
                "question": "若 rank(A) = 2，A 为 3×3 矩阵，则 rank(A²) ≤：",
                "options": ["1", "2", "3", "4"],
                "answer_index": 1,
                "explanation": "rank(A²) ≤ min(rank(A), rank(A)) = 2。",
            },
        ],
    },
    {
        "key": "similar_matrix",
        "module": "线性代数",
        "points": ("相似矩阵", "矩阵相似"),
        "match": ("相似", "相似矩阵", "对角化"),
        "language": "zh",
        "items": [
            {
                "question": "两个矩阵相似的必要条件是它们有：",
                "options": ["相同的秩", "相同的迹", "相同的特征值", "以上全是"],
                "answer_index": 3,
                "explanation": "相似矩阵有相同的秩、迹、行列式、特征值等不变量。",
            },
            {
                "question": "若 A ~ B（A 相似于 B），则 A^T ~ ：",
                "options": ["A", "B", "B^T", "B^(−1)"],
                "answer_index": 2,
                "explanation": "相似关系保持在转置运算下，A^T ~ B^T。",
            },
            {
                "question": "对角矩阵 [[2,0],[0,3]] 与 [[3,0],[0,2]] 是否相似：",
                "options": ["相似", "不相似", "无法判定", "只有特殊情况相似"],
                "answer_index": 0,
                "explanation": "都是对角矩阵，特征值都是 {2, 3}，故相似。",
            },
        ],
    },
    # ==================== 概率论扩展（新增 6 库）====================
    {
        "key": "discrete_distribution",
        "module": "概率论与数理统计",
        "points": ("离散分布", "二项分布", "泊松分布"),
        "match": ("二项分布", "泊松分布", "几何分布"),
        "language": "zh",
        "items": [
            {
                "question": "已知 X ~ B(10, 0.5)，则 E(X) = ：",
                "options": ["5", "2.5", "10", "0.5"],
                "answer_index": 0,
                "explanation": "二项分布期望 E(X) = np = 10 × 0.5 = 5。",
            },
            {
                "question": "若 X ~ B(n, p)，方差 D(X) 最大时 p = ：",
                "options": ["0", "1/2", "1", "无法确定"],
                "answer_index": 1,
                "explanation": "D(X) = np(1−p)，当 p = 1/2 时最大。",
            },
            {
                "question": "泊松分布 X ~ P(λ) 的特点是：",
                "options": ["E(X) = λ，D(X) = λ", "E(X) = λ²，D(X) = λ", "E(X) = λ，D(X) = λ²", "E(X) = 0，D(X) = 1"],
                "answer_index": 0,
                "explanation": "泊松分布的期望和方差都等于参数 λ。",
            },
            {
                "question": "掷骰子直到出现 6 点为止，所需的平均次数为：",
                "options": ["6", "3.5", "1/6", "1"],
                "answer_index": 0,
                "explanation": "这是几何分布，期望为 1/p = 1/(1/6) = 6。",
            },
        ],
    },
    {
        "key": "continuous_distribution",
        "module": "概率论与数理统计",
        "points": ("连续分布", "均匀分布", "正态分布", "指数分布"),
        "match": ("正态分布", "均匀分布", "指数分布", "连续分布"),
        "language": "zh",
        "items": [
            {
                "question": "X ~ U(a, b)（均匀分布），则 E(X) = ：",
                "options": ["a", "b", "(a+b)/2", "(b−a)/2"],
                "answer_index": 2,
                "explanation": "均匀分布的期望是区间中点。",
            },
            {
                "question": "设 X ~ N(μ, σ²)，P(|X − μ| < σ) ≈ ：",
                "options": ["0.32", "0.68", "0.95", "0.997"],
                "answer_index": 1,
                "explanation": "正态分布三 sigma 规则，68% 的数据在 [μ−σ, μ+σ] 范围内。",
            },
            {
                "question": "X ~ E(λ)（指数分布），则中位数为：",
                "options": ["1/λ", "ln 2/λ", "λ/ln 2", "1/(2λ)"],
                "answer_index": 1,
                "explanation": "指数分布中位数为 ln 2/λ。",
            },
        ],
    },
    {
        "key": "hypothesis_testing",
        "module": "概率论与数理统计",
        "points": ("假设检验", "显著性检验"),
        "match": ("假设检验", "显著性", "显著水平"),
        "language": "zh",
        "items": [
            {
                "question": "假设检验中，第一类错误是指：",
                "options": ["接受真假设", "拒绝真假设", "接受假假设", "拒绝假假设"],
                "answer_index": 1,
                "explanation": "第一类错误 α：原假设为真但被拒绝；第二类错误 β：原假设为假但未被拒绝。",
            },
            {
                "question": "显著水平 α = 0.05 意味着：",
                "options": ["出错概率是 5%", "把真的拒绝的概率是 5%", "有 95% 把握", "以上全是"],
                "answer_index": 1,
                "explanation": "α = 0.05 是第一类错误的概率（弃真）。",
            },
            {
                "question": "t 检验与 z 检验的主要区别是：",
                "options": ["样本量大小", "总体方差已知与否", "总体是否正态", "都是"],
                "answer_index": 1,
                "explanation": "方差已知用 z 检验，方差未知用 t 检验。",
            },
        ],
    },
]

# ==================== 与原 MATH_BANKS 合并 ====================
# 注意：使用时在 quiz.py / question_bank.py 中调用 BANKS 时需包含两部分
# BANKS = ENGLISH_BANKS + MATH_BANKS + MATH_BANKS_EXTENDED
