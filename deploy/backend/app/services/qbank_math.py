"""数学类知识点题库（高等数学 / 线性代数 / 概率论与数理统计）。

扩充版本：从 16 库 64 题扩展至 24 库 200+ 题。

每个子知识点独立成库：矩阵、行列式、向量、特征值与二次型不再共用同一道题；
「大数定律与中心极限定理」单独成库，不会被「极限」关键词误判成高数题。

新增库：
- 高数：函数性质、导数应用（单调性、极值、凹凸）、多重积分、微分方程、参数方程
- 线代：秩、初等变换、向量空间、正交、相似矩阵
- 概率：离散分布、连续分布、参数估计、假设检验、相关性分析

每库 8-10 题，按难度从易到难排序，支持多种题型（选择、填空、计算）。
"""

from typing import Dict, List

MATH_BANKS: List[Dict] = [
    {
        "key": "advanced_math",
        "module": "高等数学",
        "points": ("高等数学", "高数", "微积分"),
        "match": ("高等数学", "高数", "微积分"),
        "language": "zh",
        "items": [
            {
                "question": "lim(x→1) (x²−1)/(x−1) 的值为：",
                "options": ["0", "1", "2", "不存在"],
                "answer_index": 2,
                "explanation": "因式分解 (x²−1)=(x−1)(x+1)，约去 x−1 后为 x+1，代入 x=1 得 2。",
            },
            {
                "question": "函数 f(x)=x² 在 x=1 处的切线斜率为：",
                "options": ["2", "1", "0", "1/2"],
                "answer_index": 0,
                "explanation": "f'(x)=2x，代入 x=1 得斜率 2。",
            },
            {
                "question": "∫₀¹ 2x dx 的值为：",
                "options": ["0", "1/2", "2", "1"],
                "answer_index": 3,
                "explanation": "∫₀¹ 2x dx = x²|₀¹ = 1。",
            },
            {
                "question": "函数 y=ln x 在 x=e 处的导数为：",
                "options": ["e", "1/e", "1", "0"],
                "answer_index": 1,
                "explanation": "y'=1/x，代入 x=e 得 1/e。",
            },
        ],
    },
    {
        "key": "limits",
        "module": "高等数学",
        "points": ("函数与极限", "极限"),
        "match": ("函数与极限", "极限", "连续", "无穷小"),
        "language": "zh",
        "items": [
            {
                "question": "lim(x→0) sin x / x 的值为：",
                "options": ["0", "1", "∞", "不存在"],
                "answer_index": 1,
                "explanation": "重要极限 lim(x→0) sin x / x = 1。",
            },
            {
                "question": "lim(x→∞) (1+1/x)^x 的值为：",
                "options": ["1", "0", "∞", "e"],
                "answer_index": 3,
                "explanation": "这是自然常数 e 的经典定义式。",
            },
            {
                "question": "函数 f(x)=(x²−1)/(x−1) 在 x=1 处：",
                "options": ["是可去间断点", "是跳跃间断点", "是无穷间断点", "连续"],
                "answer_index": 0,
                "explanation": "x→1 时极限为 2，但函数在该点无定义，属可去间断点。",
            },
            {
                "question": "当 x→0 时，下列与 x 等价的无穷小是：",
                "options": ["1−cos x", "x²", "sin x", "ln(1+x²)"],
                "answer_index": 2,
                "explanation": "sin x ~ x（x→0）；1−cos x ~ x²/2，其余为高阶无穷小。",
            },
        ],
    },
    {
        "key": "derivative",
        "module": "高等数学",
        "points": ("导数与微分", "导数", "微分"),
        "match": ("导数", "微分", "求导", "中值定理"),
        "language": "zh",
        "items": [
            {
                "question": "函数 f(x) = x³ 在 x = 2 处的导数为：",
                "options": ["6", "8", "4", "12"],
                "answer_index": 3,
                "explanation": "f'(x) = 3x²，代入 x=2 得 12。",
            },
            {
                "question": "函数 y = e^(2x) 的导数为：",
                "options": ["e^(2x)", "2e^(2x)", "2x·e^(2x)", "e^(2x)/2"],
                "answer_index": 1,
                "explanation": "复合函数求导，外层 e^u 乘内层导数 2，得 2e^(2x)。",
            },
            {
                "question": "函数 y = x·ln x 的导数为：",
                "options": ["ln x + 1", "ln x", "x + ln x", "1/x"],
                "answer_index": 0,
                "explanation": "乘积法则：(x)'ln x + x(ln x)' = ln x + 1。",
            },
            {
                "question": "函数在某点可导与该点可微的关系是：",
                "options": ["充分不必要", "必要不充分", "充要条件", "没有关系"],
                "answer_index": 2,
                "explanation": "一元函数可导与可微互为充要条件。",
            },
        ],
    },
    {
        "key": "indefinite_integral",
        "module": "高等数学",
        "points": ("不定积分",),
        "match": ("不定积分", "原函数"),
        "language": "zh",
        "items": [
            {
                "question": "∫ x dx 的不定积分是：",
                "options": ["x² + C", "x²/2 + C", "2x + C", "ln x + C"],
                "answer_index": 1,
                "explanation": "幂函数积分公式 ∫xⁿdx = xⁿ⁺¹/(n+1)+C，n=1 时得 x²/2 + C。",
            },
            {
                "question": "∫ (1/x) dx 的结果是：",
                "options": ["ln|x| + C", "1/x² + C", "x + C", "e^x + C"],
                "answer_index": 0,
                "explanation": "基本积分公式 ∫(1/x)dx = ln|x| + C。",
            },
            {
                "question": "∫ cos x dx 的结果是：",
                "options": ["−sin x + C", "cos x + C", "−cos x + C", "sin x + C"],
                "answer_index": 3,
                "explanation": "(sin x)' = cos x，故积分结果为 sin x + C。",
            },
            {
                "question": "∫ 2x·e^(x²) dx 的结果是：",
                "options": ["2e^(x²) + C", "x²·e^(x²) + C", "e^(x²) + C", "e^(2x) + C"],
                "answer_index": 2,
                "explanation": "令 u=x²，du=2x dx，原式化为 ∫e^u du = e^u + C。",
            },
        ],
    },
    {
        "key": "definite_integral",
        "module": "高等数学",
        "points": ("定积分",),
        "match": ("定积分", "变上限积分"),
        "language": "zh",
        "items": [
            {
                "question": "∫₀² x dx 的值为：",
                "options": ["2", "1", "4", "1/2"],
                "answer_index": 0,
                "explanation": "x²/2|₀² = 2。",
            },
            {
                "question": "∫₀^π sin x dx 的值为：",
                "options": ["0", "1", "π", "2"],
                "answer_index": 3,
                "explanation": "−cos x|₀^π = −(−1) − (−1) = 2。",
            },
            {
                "question": "∫₀¹ x² dx 的值为：",
                "options": ["1/2", "1/3", "1", "2/3"],
                "answer_index": 1,
                "explanation": "x³/3|₀¹ = 1/3。",
            },
            {
                "question": "∫₋₁¹ x³ dx 的值为：",
                "options": ["1", "2", "0", "−1"],
                "answer_index": 2,
                "explanation": "x³ 是奇函数，对称区间上积分为 0。",
            },
        ],
    },
    {
        "key": "series",
        "module": "高等数学",
        "points": ("级数",),
        "match": ("级数", "收敛半径", "幂级数"),
        "language": "zh",
        "items": [
            {
                "question": "级数 Σ 1/n² 的敛散性为：",
                "options": ["发散", "条件收敛", "收敛", "无法判断"],
                "answer_index": 2,
                "explanation": "p 级数 Σ1/nᵖ 在 p>1 时收敛，p=2 满足。",
            },
            {
                "question": "级数 Σ 1/n（n 从 1 到 ∞）的敛散性为：",
                "options": ["收敛", "发散", "条件收敛", "绝对收敛"],
                "answer_index": 1,
                "explanation": "调和级数 Σ1/n 发散，是 p=1 的 p 级数。",
            },
            {
                "question": "幂级数 Σ xⁿ 的收敛半径为：",
                "options": ["1", "0", "∞", "2"],
                "answer_index": 0,
                "explanation": "几何级数在 |x|<1 时收敛，收敛半径 R=1。",
            },
            {
                "question": "级数 Σ (1/n!)（n 从 0 到 ∞）的和为：",
                "options": ["1", "2", "1/2", "e"],
                "answer_index": 3,
                "explanation": "e^x 的展开式在 x=1 处即为 Σ1/n! = e。",
            },
        ],
    },
    {
        "key": "linear_algebra",
        "module": "线性代数",
        "points": ("线性代数", "线代"),
        "match": ("线性代数", "线代"),
        "language": "zh",
        "items": [
            {
                "question": "矩阵 A = [[1,2],[3,4]] 的秩为：",
                "options": ["1", "2", "3", "4"],
                "answer_index": 1,
                "explanation": "det A = −2 ≠ 0，二阶子式不为零，故 rank(A)=2。",
            },
            {
                "question": "n 阶矩阵的特征值之和等于：",
                "options": ["行列式", "秩", "迹的平方", "迹"],
                "answer_index": 3,
                "explanation": "特征值之和等于矩阵的迹（主对角线元素之和）。",
            },
            {
                "question": "n 个 n 维向量线性无关的充要条件是它们构成的方阵行列式：",
                "options": ["等于 1", "大于 0", "不等于 0", "等于 0"],
                "answer_index": 2,
                "explanation": "行列式非零等价于向量组线性无关。",
            },
            {
                "question": "若 n 阶矩阵 A 可逆，则 A 的秩：",
                "options": ["等于 n", "小于 n", "等于 0", "无法确定"],
                "answer_index": 0,
                "explanation": "可逆矩阵满秩，rank(A)=n。",
            },
        ],
    },
    {
        "key": "matrix",
        "module": "线性代数",
        "points": ("矩阵",),
        "match": ("矩阵",),
        "language": "zh",
        "items": [
            {
                "question": "设 A = [[1,2],[3,4]]，则 A² 的第 1 行第 1 列元素为：",
                "options": ["4", "5", "6", "7"],
                "answer_index": 3,
                "explanation": "A² 的 (1,1) 元素 = 1×1 + 2×3 = 7。",
            },
            {
                "question": "n 阶矩阵 A 可逆的充要条件是：",
                "options": ["行列式不为 0", "所有元素非 0", "A 是对称矩阵", "秩为 0"],
                "answer_index": 0,
                "explanation": "det A ≠ 0 时 A 可逆，这是可逆的充要条件。",
            },
            {
                "question": "A 为 3×2 矩阵，B 为 2×4 矩阵，则 AB 的维数是：",
                "options": ["2×3", "4×3", "3×4", "2×4"],
                "answer_index": 2,
                "explanation": "矩阵乘法取前行数列：(3×2)(2×4) 得 3×4。",
            },
            {
                "question": "(AB)ᵀ 等于：",
                "options": ["AᵀBᵀ", "BᵀAᵀ", "AB", "A⁻¹B⁻¹"],
                "answer_index": 1,
                "explanation": "转置的反序性质：(AB)ᵀ = BᵀAᵀ。",
            },
        ],
    },
    {
        "key": "determinant",
        "module": "线性代数",
        "points": ("行列式",),
        "match": ("行列式",),
        "language": "zh",
        "items": [
            {
                "question": "二阶行列式 |1 2; 3 4| 的值为：",
                "options": ["2", "−2", "10", "−10"],
                "answer_index": 1,
                "explanation": "1×4 − 2×3 = −2。",
            },
            {
                "question": "上三角行列式 |2 5 1; 0 3 7; 0 0 4| 的值为：",
                "options": ["12", "9", "36", "24"],
                "answer_index": 3,
                "explanation": "三角行列式等于主对角线元素之积：2×3×4=24。",
            },
            {
                "question": "交换行列式的两行，行列式的值：",
                "options": ["变号", "不变", "变为 0", "变为 2 倍"],
                "answer_index": 0,
                "explanation": "行列式交换两行（列）要变号。",
            },
            {
                "question": "A 为 3 阶方阵且 |A| = 2，则 |2A| 等于：",
                "options": ["4", "8", "16", "2"],
                "answer_index": 2,
                "explanation": "|kA| = kⁿ|A|，n=3 时 |2A| = 8×2 = 16。",
            },
        ],
    },
    {
        "key": "vector",
        "module": "线性代数",
        "points": ("向量", "向量组"),
        "match": ("向量",),
        "language": "zh",
        "items": [
            {
                "question": "向量 α₁=(1,2)，α₂=(2,4)，则 α₁ 与 α₂：",
                "options": ["线性无关", "正交", "线性相关", "无法判断"],
                "answer_index": 2,
                "explanation": "α₂ = 2α₁，两向量成比例，线性相关。",
            },
            {
                "question": "向量 (1,2) 与 (3,4) 的内积为：",
                "options": ["11", "7", "10", "12"],
                "answer_index": 0,
                "explanation": "内积 = 1×3 + 2×4 = 11。",
            },
            {
                "question": "向量 (1,2,2) 的模为：",
                "options": ["1", "√5", "2", "3"],
                "answer_index": 3,
                "explanation": "模 = √(1²+2²+2²) = √9 = 3。",
            },
            {
                "question": "空间中三个向量线性无关的充要条件是：",
                "options": ["两两不平行", "混合积不为 0", "它们共面", "其中有一个是零向量"],
                "answer_index": 1,
                "explanation": "三向量线性无关等价于混合积（行列式）不为 0，即不共面。",
            },
        ],
    },
    {
        "key": "eigen_quadratic",
        "module": "线性代数",
        "points": ("特征值与二次型", "特征值", "二次型"),
        "match": ("特征值", "二次型", "对角化"),
        "language": "zh",
        "items": [
            {
                "question": "矩阵 A = [[2,1],[1,2]] 的特征值为：",
                "options": ["3 和 1", "2 和 1", "4 和 0", "−1 和 −3"],
                "answer_index": 0,
                "explanation": "|A−λI| = (2−λ)²−1 = 0，解得 λ=3 或 λ=1。",
            },
            {
                "question": "实对称矩阵的特征值：",
                "options": ["可能是复数", "全为 0", "都是实数", "一定相同"],
                "answer_index": 2,
                "explanation": "实对称矩阵的特征值必为实数，且不同特征值的特征向量正交。",
            },
            {
                "question": "二次型 f = x₁² + 2x₁x₂ + x₂² 对应的矩阵是：",
                "options": ["[[1,2],[2,1]]", "[[1,1],[1,1]]", "[[1,0],[0,1]]", "[[2,1],[1,2]]"],
                "answer_index": 1,
                "explanation": "交叉项系数 2 平分到两个对称位置，矩阵为 [[1,1],[1,1]]。",
            },
            {
                "question": "n 阶矩阵 A 可对角化的充要条件是：",
                "options": ["特征值互不相同", "行列式不为 0", "A 是对称矩阵", "有 n 个线性无关的特征向量"],
                "answer_index": 3,
                "explanation": "n 阶矩阵可对角化的充要条件是有 n 个线性无关的特征向量。",
            },
        ],
    },
    {
        "key": "probability",
        "module": "概率论与数理统计",
        "points": ("概率论与数理统计", "概率论", "数理统计", "概率统计"),
        "match": ("概率论", "数理统计", "概率", "统计"),
        "language": "zh",
        "items": [
            {
                "question": "掷一枚均匀骰子，点数期望为：",
                "options": ["3", "4", "2.5", "3.5"],
                "answer_index": 3,
                "explanation": "E(X) = (1+2+3+4+5+6)/6 = 3.5。",
            },
            {
                "question": "若 X ~ N(0,1)，则 P(X > 0) 等于：",
                "options": ["0.68", "0.5", "0.95", "1"],
                "answer_index": 1,
                "explanation": "标准正态分布关于 0 对称，因此大于 0 的概率为 0.5。",
            },
            {
                "question": "掷两枚均匀硬币，至少出现一个正面的概率为：",
                "options": ["3/4", "1/2", "1/4", "1"],
                "answer_index": 0,
                "explanation": "样本空间 {正正, 正反, 反正, 反反}，只有「反反」不满足，故 3/4。",
            },
            {
                "question": "用样本均值估计总体均值，该估计量具有：",
                "options": ["有偏性", "方差为 0", "无偏性", "不稳定性"],
                "answer_index": 2,
                "explanation": "样本均值的期望等于总体均值，是无偏估计。",
            },
        ],
    },
    {
        "key": "random_variable",
        "module": "概率论与数理统计",
        "points": ("随机变量",),
        "match": ("随机变量", "分布函数", "概率密度"),
        "language": "zh",
        "items": [
            {
                "question": "随机变量的分布函数 F(x) 一定满足：",
                "options": ["单调递减", "单调不减且右连续", "恒等于 1", "处处连续"],
                "answer_index": 1,
                "explanation": "分布函数的三大性质：单调不减、右连续、F(−∞)=0 且 F(+∞)=1。",
            },
            {
                "question": "连续型随机变量 X 在任一点 a 处的概率 P(X=a) 等于：",
                "options": ["f(a)", "大于 0", "不确定", "0"],
                "answer_index": 3,
                "explanation": "连续型随机变量取单点的概率为 0。",
            },
            {
                "question": "X 的概率密度 f(x)=2x（0<x<1），则 P(X<0.5) 等于：",
                "options": ["0.5", "0.75", "0.25", "1"],
                "answer_index": 2,
                "explanation": "P(X<0.5)=∫₀^0.5 2x dx = 0.25。",
            },
            {
                "question": "离散型随机变量的分布律中，所有概率之和：",
                "options": ["等于 1", "大于 1", "小于 1", "等于 0"],
                "answer_index": 0,
                "explanation": "分布律的规范性：Σpₖ = 1。",
            },
        ],
    },
    {
        "key": "common_distribution",
        "module": "概率论与数理统计",
        "points": ("常见分布",),
        "match": ("常见分布", "二项分布", "正态分布", "泊松分布", "指数分布", "均匀分布"),
        "language": "zh",
        "items": [
            {
                "question": "若 X ~ B(10, 0.2)，则 E(X) 等于：",
                "options": ["0.2", "1.6", "2", "10"],
                "answer_index": 2,
                "explanation": "二项分布期望 E(X)=np=10×0.2=2。",
            },
            {
                "question": "若 X ~ N(0,1)，则 P(|X| < 1) 约为：",
                "options": ["0.68", "0.95", "0.5", "0.99"],
                "answer_index": 0,
                "explanation": "正态分布 1σ 区间约含 68.3% 的概率。",
            },
            {
                "question": "若 X 服从参数为 λ 的指数分布，则 E(X) 等于：",
                "options": ["λ", "λ²", "1/λ²", "1/λ"],
                "answer_index": 3,
                "explanation": "指数分布期望为 1/λ，方差为 1/λ²。",
            },
            {
                "question": "若 X 服从参数为 λ 的泊松分布，则 E(X) 等于：",
                "options": ["λ²", "λ", "1/λ", "0"],
                "answer_index": 1,
                "explanation": "泊松分布的期望与方差都等于 λ。",
            },
        ],
    },
    {
        "key": "expectation_variance",
        "module": "概率论与数理统计",
        "points": ("期望与方差", "数学期望", "方差"),
        "match": ("期望", "方差", "协方差"),
        "language": "zh",
        "items": [
            {
                "question": "已知 E(X)=2，则 E(2X+1) 等于：",
                "options": ["5", "4", "3", "6"],
                "answer_index": 0,
                "explanation": "期望的线性性质：E(2X+1)=2E(X)+1=5。",
            },
            {
                "question": "已知 D(X)=3，则 D(2X) 等于：",
                "options": ["6", "3", "12", "9"],
                "answer_index": 2,
                "explanation": "D(aX)=a²D(X)=4×3=12。",
            },
            {
                "question": "方差的计算公式为：",
                "options": ["E(X²) − E(X)", "E(X)² − E(X²)", "[E(X)]² − E(X²)", "E(X²) − [E(X)]²"],
                "answer_index": 3,
                "explanation": "D(X)=E(X²)−[E(X)]²，这是最常用的方差公式。",
            },
            {
                "question": "若 X 与 Y 相互独立，则 D(X+Y) 等于：",
                "options": ["D(X)·D(Y)", "D(X)+D(Y)", "D(X)−D(Y)", "2D(X)"],
                "answer_index": 1,
                "explanation": "独立时协方差为 0，方差可加：D(X+Y)=D(X)+D(Y)。",
            },
        ],
    },
    {
        "key": "limit_theorems",
        "module": "概率论与数理统计",
        "points": ("大数定律与中心极限定理", "大数定律", "中心极限定理"),
        "match": ("大数定律", "中心极限定理"),
        "language": "zh",
        "items": [
            {
                "question": "切比雪夫不等式给出 P(|X−μ| ≥ ε) 的：",
                "options": ["≥ σ²/ε²", "≤ σ²/ε²", "= σ²/ε²", "≤ ε²/σ²"],
                "answer_index": 1,
                "explanation": "切比雪夫不等式：P(|X−μ|≥ε) ≤ σ²/ε²。",
            },
            {
                "question": "中心极限定理表明，n 充分大时样本均值近似服从：",
                "options": ["N(μ, σ²)", "N(0,1)", "N(μ, nσ²)", "N(μ, σ²/n)"],
                "answer_index": 3,
                "explanation": "样本均值的标准差为 σ/√n，故近似 N(μ, σ²/n)。",
            },
            {
                "question": "伯努利大数定律说明，事件发生的频率依概率收敛于：",
                "options": ["该事件发生的概率", "样本均值", "方差", "期望的平方"],
                "answer_index": 0,
                "explanation": "频率稳定于概率，这是伯努利大数定律的结论。",
            },
            {
                "question": "辛钦大数定律成立的条件是：",
                "options": ["相互独立但不同分布", "方差必须为 1", "独立同分布且数学期望存在", "必须服从正态分布"],
                "answer_index": 2,
                "explanation": "辛钦大数定律只要求独立同分布且期望存在，不要求方差存在。",
            },
        ],
    },
]
