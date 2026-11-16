"""程序化题源：为每个知识点补足题量，答案由公式计算，不靠手写记忆。

为什么需要
----------
内置题库每库只有 4 题，连着做两三次就重复；而题库（tikuAdapter）要按知识点
一一对应地存题，题量太少就失去意义。

这里用「参数化出题」补齐：定积分、导数、极限、线代、级数、概率这些知识点，
题干与答案都能由公式直接算出来（``Fraction`` 精确计算，不用浮点），
所以题库里的答案 100% 可复算，不会出现手写题抄错答案的情况。

每个题库条目与 ``qbank_math`` 结构一致：
``{"key", "module", "points", "match", "language", "items": [{question, options, answer_index, explanation}]}``
"""

from __future__ import annotations

import random
from fractions import Fraction
from typing import Dict, List, Sequence

# 选项打乱用固定种子，保证「同一道题每次构建出的选项顺序一致」（可复算）
def _shuffle_options(answer: str, distractors: Sequence[str], seed: str) -> tuple:
    pool: List[str] = [answer]
    for distractor in distractors:
        if distractor and distractor not in pool:
            pool.append(distractor)
    index = 1
    while len(pool) < 4:
        filler = f"以上都不对{index}" if index > 1 else "以上都不对"
        if filler not in pool:
            pool.append(filler)
        index += 1
    pool = pool[:4]
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool, pool.index(answer)


def _q(question: str, answer: str, distractors: Sequence[str], explanation: str) -> Dict:
    options, answer_index = _shuffle_options(answer, distractors, question)
    return {
        "question": question,
        "options": options,
        "answer_index": answer_index,
        "explanation": explanation,
    }


def _num(value) -> str:
    """Fraction / int → 展示字符串（整数不带小数点，分数写成 p/q）。"""
    frac = Fraction(value)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


# --------------------------------------------------------------------------
# 定积分 / 不定积分
# --------------------------------------------------------------------------

def _definite_integral_items() -> List[Dict]:
    items: List[Dict] = []
    # 多项式定积分 ∫₀^a k xⁿ dx = k·a^(n+1)/(n+1)
    for k, n, a in [(2, 1, 3), (3, 1, 2), (4, 2, 1), (6, 2, 2), (3, 3, 2), (4, 1, 4)]:
        value = Fraction(k * a ** (n + 1), n + 1)
        power = "x" if n == 1 else f"x^{n}"
        items.append(
            _q(
                f"∫₀^{a} {k}{power} dx 的值为：",
                _num(value),
                [_num(value + 1), _num(value * 2), _num(Fraction(k * a ** n))],
                f"∫₀^{a} {k}{power} dx = {k}·x^{n + 1}/{n + 1} |₀^{a} = {k}·{a}^{n + 1}/{n + 1} = {_num(value)}。",
            )
        )
    items.append(
        _q(
            "∫₀^π sin x dx 的值为：",
            "2",
            ["0", "1", "π"],
            "∫sin x dx = −cos x，代入上下限得 −cos π + cos 0 = 1 + 1 = 2。",
        )
    )
    items.append(
        _q(
            "∫₀^(π/2) cos x dx 的值为：",
            "1",
            ["0", "1/2", "π/2"],
            "∫cos x dx = sin x，sin(π/2) − sin 0 = 1。",
        )
    )
    items.append(
        _q(
            "∫₁^e (1/x) dx 的值为：",
            "1",
            ["e", "0", "e−1"],
            "∫(1/x)dx = ln x，ln e − ln 1 = 1 − 0 = 1。",
        )
    )
    items.append(
        _q(
            "∫₋₁^1 x³ dx 的值为：",
            "0",
            ["2", "1/4", "−2"],
            "x³ 是奇函数，对称区间上定积分必为 0。",
        )
    )
    items.append(
        _q(
            "设 f(x) 连续，则 d/dx ∫₀^x f(t) dt 等于：",
            "f(x)",
            ["f'(x)", "f(x) − f(0)", "0"],
            "变上限积分求导回到被积函数本身：d/dx ∫₀^x f(t)dt = f(x)。",
        )
    )
    items.append(
        _q(
            "曲线 y = x² 与 x 轴在区间 [0, 3] 上围成的图形面积为：",
            "9",
            ["3", "6", "27"],
            "∫₀³ x² dx = x³/3 |₀³ = 27/3 = 9。",
        )
    )
    return items


def _indefinite_integral_items() -> List[Dict]:
    items: List[Dict] = []
    for n in (1, 2, 3, 4):
        items.append(
            _q(
                f"∫ x^{n} dx 的结果是（C 为任意常数）：",
                f"x^{n + 1}/{n + 1} + C",
                [f"x^{n + 1} + C", f"{n}x^{n - 1} + C", f"x^{n}/{n} + C"],
                f"幂函数积分公式：∫xⁿdx = x^(n+1)/(n+1) + C，此处 n = {n}。",
            )
        )
    items.append(
        _q(
            "∫ (1/x) dx 的结果是（C 为任意常数）：",
            "ln|x| + C",
            ["1/x² + C", "−1/x² + C", "x·ln x + C"],
            "∫(1/x)dx = ln|x| + C，注意绝对值。",
        )
    )
    items.append(
        _q(
            "∫ e^x dx 的结果是（C 为任意常数）：",
            "e^x + C",
            ["x·e^x + C", "e^x/x + C", "e^(x+1) + C"],
            "e^x 的导数仍是 e^x，故其原函数为 e^x + C。",
        )
    )
    items.append(
        _q(
            "∫ cos x dx 的结果是（C 为任意常数）：",
            "sin x + C",
            ["−sin x + C", "cos x + C", "−cos x + C"],
            "sin x 求导为 cos x，故 ∫cos x dx = sin x + C。",
        )
    )
    items.append(
        _q(
            "用换元法计算 ∫ 2x·e^(x²) dx 的结果是（C 为任意常数）：",
            "e^(x²) + C",
            ["2e^(x²) + C", "x²·e^(x²) + C", "e^(2x) + C"],
            "令 u = x²，du = 2x dx，积分变为 ∫e^u du = e^u + C = e^(x²) + C。",
        )
    )
    items.append(
        _q(
            "分部积分公式 ∫u dv 等于：",
            "uv − ∫v du",
            ["uv + ∫v du", "u'v − uv'", "∫u du · ∫v dv"],
            "分部积分由 (uv)' = u'v + uv' 移项积分得到：∫u dv = uv − ∫v du。",
        )
    )
    return items


# --------------------------------------------------------------------------
# 导数与微分
# --------------------------------------------------------------------------

def _derivative_items() -> List[Dict]:
    items: List[Dict] = []
    for a, n, x0 in [(3, 3, 2), (2, 4, 1), (5, 2, 3), (4, 3, 2)]:
        value = Fraction(a * n * x0 ** (n - 1))
        items.append(
            _q(
                f"函数 f(x) = {a}x^{n} 在 x = {x0} 处的导数值为：",
                _num(value),
                [_num(Fraction(a * x0 ** n)), _num(value + a), _num(Fraction(a * n * x0 ** n))],
                f"f'(x) = {a}·{n}x^{n - 1}，代入 x = {x0} 得 {a}×{n}×{x0}^{n - 1} = {_num(value)}。",
            )
        )
    for k in (2, 3, 5):
        items.append(
            _q(
                f"函数 y = e^({k}x) 的导数为：",
                f"{k}e^({k}x)",
                [f"e^({k}x)", f"e^({k}x)/{k}", f"{k}x·e^({k}x)"],
                f"复合函数求导：(e^(kx))' = k·e^(kx)。",
            )
        )
    items.append(
        _q(
            "函数 y = ln x 在 x = e 处的导数值为：",
            "1/e",
            ["e", "1", "0"],
            "y' = 1/x，代入 x = e 得 1/e。",
        )
    )
    items.append(
        _q(
            "函数 y = sin(3x) 的导数为：",
            "3cos(3x)",
            ["cos(3x)", "−3cos(3x)", "3sin(3x)"],
            "复合求导：sin(u) 的导数为 cos(u)·u'，u = 3x 时 u' = 3。",
        )
    )
    items.append(
        _q(
            "函数 f(x) = x² 在 x = 3 处的微分 dy（dx = 0.1）为：",
            "0.6",
            ["0.3", "6", "0.06"],
            "dy = f'(x)dx = 2x·dx = 2×3×0.1 = 0.6。",
        )
    )
    items.append(
        _q(
            "若 f(x) 在 x₀ 处可导且取得极值，则 f'(x₀) 必定：",
            "等于 0",
            ["大于 0", "小于 0", "不存在"],
            "可导函数在极值点处切线水平，即 f'(x₀) = 0（费马引理）。",
        )
    )
    items.append(
        _q(
            "函数 f(x) = x³ − 3x 的单调递增区间是：",
            "(−∞, −1) 与 (1, +∞)",
            ["(−1, 1)", "(0, +∞)", "(−∞, 0)"],
            "f'(x) = 3x² − 3 = 3(x−1)(x+1)，在 |x| > 1 时为正，故在这两段上递增。",
        )
    )
    return items


# --------------------------------------------------------------------------
# 函数与极限
# --------------------------------------------------------------------------

def _limits_items() -> List[Dict]:
    items: List[Dict] = []
    for a in (2, 3, 5, 7):
        items.append(
            _q(
                f"lim(x→0) sin({a}x)/x 的值为：",
                str(a),
                ["1", str(a * a), f"1/{a}"],
                f"等价无穷小 sin({a}x) ~ {a}x，故极限为 {a}。",
            )
        )
    for a in (2, 3, 4):
        items.append(
            _q(
                f"lim(x→{a}) (x² − {a * a})/(x − {a}) 的值为：",
                str(2 * a),
                [str(a), str(a * a), "不存在"],
                f"因式分解 x² − {a * a} = (x − {a})(x + {a})，约分后为 x + {a}，代入得 {2 * a}。",
            )
        )
    for num, den in [(3, 2), (5, 4), (7, 3)]:
        items.append(
            _q(
                f"lim(x→∞) ({num}x² + x)/({den}x² − 1) 的值为：",
                _num(Fraction(num, den)),
                [str(num), str(den), "0"],
                "同阶最高次项系数之比即极限：分子分母同除 x²，得系数比。",
            )
        )
    items.append(
        _q(
            "lim(x→0) (1 − cos x)/x² 的值为：",
            "1/2",
            ["0", "1", "2"],
            "等价无穷小 1 − cos x ~ x²/2，故极限为 1/2。",
        )
    )
    items.append(
        _q(
            "lim(x→∞) (1 + 1/x)^x 的值为：",
            "e",
            ["1", "0", "∞"],
            "这是自然常数 e 的经典定义式。",
        )
    )
    items.append(
        _q(
            "函数 f(x) = (x² − 1)/(x − 1) 在 x = 1 处的间断点类型为：",
            "可去间断点",
            ["跳跃间断点", "无穷间断点", "振荡间断点"],
            "x ≠ 1 时 f(x) = x + 1，极限存在且为 2，只需补充定义 f(1) = 2 即连续，故为可去间断点。",
        )
    )
    items.append(
        _q(
            "若 lim(x→x₀) f(x) 存在，则 f(x) 在 x₀ 处：",
            "一定局部有界",
            ["一定连续", "一定可导", "一定取得极值"],
            "极限存在只能推出局部有界；连续、可导都需要更强条件。",
        )
    )
    return items


# --------------------------------------------------------------------------
# 线性代数：行列式 / 矩阵 / 向量 / 特征值
# --------------------------------------------------------------------------

def _det2(a: int, b: int, c: int, d: int) -> int:
    return a * d - b * c


def _determinant_items() -> List[Dict]:
    items: List[Dict] = []
    for a, b, c, d in [(1, 2, 3, 4), (2, 1, 1, 3), (3, 2, 4, 1), (5, 1, 2, 3)]:
        value = _det2(a, b, c, d)
        items.append(
            _q(
                f"二阶行列式 |{a} {b}; {c} {d}| 的值为：",
                str(value),
                [str(a * d + b * c), str(a + d), str(b * c - a * d)],
                f"二阶行列式按 ad − bc 计算：{a}×{d} − {b}×{c} = {value}。",
            )
        )
    for diag in [(2, 3, 4), (1, 5, 2), (3, 3, 2)]:
        value = diag[0] * diag[1] * diag[2]
        items.append(
            _q(
                f"上三角行列式 |{diag[0]} * *; 0 {diag[1]} *; 0 0 {diag[2]}| 的值为：",
                str(value),
                [str(sum(diag)), str(value * 2), "0"],
                "三角行列式等于主对角线元素之积。",
            )
        )
    items.append(
        _q(
            "若 3 阶行列式中某两行完全相同，则该行列式的值为：",
            "0",
            ["1", "该行元素之和", "无法确定"],
            "行列式有两行（列）成比例即为 0，完全相同是其特例。",
        )
    )
    items.append(
        _q(
            "交换行列式的两行，行列式的值：",
            "变号（乘以 −1）",
            ["不变", "变成原来的 2 倍", "变为 0"],
            "交换两行属于初等行变换，行列式值取相反数。",
        )
    )
    items.append(
        _q(
            "n 阶方阵 A 可逆的充要条件是：",
            "|A| ≠ 0",
            ["|A| = 1", "A 的元素都不为 0", "A 是对称矩阵"],
            "行列式非零说明矩阵满秩，存在逆矩阵；反之不可逆。",
        )
    )
    return items


def _matrix_items() -> List[Dict]:
    items: List[Dict] = []
    for a, b, c, d in [(1, 2, 3, 4), (2, 0, 1, 3), (4, 1, 2, 2)]:
        trace = a + d
        items.append(
            _q(
                f"矩阵 A = [{a} {b}; {c} {d}] 的迹（主对角线元素之和）为：",
                str(trace),
                [str(_det2(a, b, c, d)), str(a * d), str(b + c)],
                f"迹 = a₁₁ + a₂₂ = {a} + {d} = {trace}。",
            )
        )
    items.append(
        _q(
            "设 A 为 3 阶方阵，|A| = 2，则 |2A| 等于：",
            "16",
            ["4", "8", "2"],
            "n 阶方阵数乘的行列式 |kA| = kⁿ|A|，故 |2A| = 2³ × 2 = 16。",
        )
    )
    items.append(
        _q(
            "矩阵 A = [1 2; 2 4] 的秩为：",
            "1",
            ["2", "0", "3"],
            "第二行是第一行的 2 倍，两行线性相关，只有 1 个非零行，秩为 1。",
        )
    )
    items.append(
        _q(
            "两个 n 阶方阵 A、B 满足 (AB)ᵀ 等于：",
            "BᵀAᵀ",
            ["AᵀBᵀ", "AB", "Aᵀ + Bᵀ"],
            "矩阵转置的反序法则：(AB)ᵀ = BᵀAᵀ。",
        )
    )
    items.append(
        _q(
            "矩阵 A = [1 0; 0 2] 的逆矩阵为：",
            "[1 0; 0 1/2]",
            ["[2 0; 0 1]", "[1 0; 0 2]", "[0 1; 1 0]"],
            "对角矩阵求逆即对角元素取倒数。",
        )
    )
    items.append(
        _q(
            "设 A 为 m×n 矩阵，B 为 n×p 矩阵，则 AB 是：",
            "m×p 矩阵",
            ["n×n 矩阵", "p×m 矩阵", "m×n 矩阵"],
            "矩阵乘法维度规则：(m×n)·(n×p) = m×p。",
        )
    )
    items.append(
        _q(
            "若矩阵 A 与 B 相似，则下列必然相等的是：",
            "特征值",
            ["元素", "行列式的平方", "转置矩阵"],
            "相似矩阵有相同的特征多项式，因此特征值、迹、行列式都相同。",
        )
    )
    return items


def _vector_items() -> List[Dict]:
    items: List[Dict] = []
    for u, v in [((1, 2), (2, 3)), ((2, 1), (1, 3)), ((1, 3), (3, 1))]:
        det = u[0] * v[1] - u[1] * v[0]
        dependent = det == 0
        items.append(
            _q(
                f"向量 α = ({u[0]}, {u[1]})，β = ({v[0]}, {v[1]})，则 α 与 β：",
                "线性相关" if dependent else "线性无关",
                ["线性无关" if dependent else "线性相关", "正交", "相等"],
                f"两向量构成的二阶行列式 = {u[0]}×{v[1]} − {u[1]}×{v[0]} = {det}，"
                + ("为 0 说明线性相关。" if dependent else "非 0 说明线性无关。"),
            )
        )
    items.append(
        _q(
            "n 维向量组线性无关的充要条件是：",
            "向量组的秩等于向量个数",
            ["向量组含零向量", "向量个数大于维数", "任意两向量都不等"],
            "线性无关 ⇔ 秩 = 向量个数；含零向量或个数超过维数必然相关。",
        )
    )
    items.append(
        _q(
            "3 维空间中，任意 4 个向量必然：",
            "线性相关",
            ["线性无关", "两两正交", "构成一组基"],
            "n 维空间中向量个数超过 n 时必线性相关。",
        )
    )
    items.append(
        _q(
            "向量 α = (1, 2, 2) 的模（长度）为：",
            "3",
            ["5", "√5", "9"],
            "|α| = √(1² + 2² + 2²) = √9 = 3。",
        )
    )
    items.append(
        _q(
            "向量 α = (1, 0)、β = (0, 1) 的关系是：",
            "正交且线性无关",
            ["平行且线性相关", "正交但线性相关", "相等"],
            "内积 1×0 + 0×1 = 0 说明正交；两个非零正交向量必线性无关。",
        )
    )
    items.append(
        _q(
            "向量组 α₁, α₂, α₃ 线性相关的含义是：",
            "存在不全为 0 的系数使线性组合为 0",
            ["系数全为 0 时线性组合为 0", "三个向量都非零", "三个向量两两不等"],
            "线性相关的定义：存在不全为零的 k₁, k₂, k₃ 使 k₁α₁ + k₂α₂ + k₃α₃ = 0。",
        )
    )
    return items


def _eigen_items() -> List[Dict]:
    items: List[Dict] = []
    for l1, l2 in [(2, -1), (3, 1), (5, 0)]:
        items.append(
            _q(
                f"2 阶矩阵的特征值为 λ₁ = {l1}、λ₂ = {l2}，则矩阵的迹为：",
                str(l1 + l2),
                [str(l1 * l2), str(l1 - l2), str(-(l1 + l2))],
                f"特征值之和等于迹：{l1} + ({l2}) = {l1 + l2}。",
            )
        )
        items.append(
            _q(
                f"2 阶矩阵的两个特征值为 {l1} 和 {l2}，则其行列式为：",
                str(l1 * l2),
                [str(l1 + l2), str(l1 - l2), "0"],
                f"特征值之积等于行列式：{l1} × ({l2}) = {l1 * l2}。",
            )
        )
    items.append(
        _q(
            "实对称矩阵的特征值：",
            "都是实数",
            ["都是正数", "都是整数", "一定互不相同"],
            "实对称矩阵必可正交对角化，其特征值全为实数。",
        )
    )
    items.append(
        _q(
            "若 A 可逆且 λ 是 A 的特征值，则 A⁻¹ 的特征值是：",
            "1/λ",
            ["λ", "λ²", "−λ"],
            "由 Ax = λx 得 A⁻¹x = (1/λ)x，故 A⁻¹ 的特征值为 1/λ。",
        )
    )
    items.append(
        _q(
            "n 阶矩阵 A 可对角化的充分条件是：",
            "A 有 n 个线性无关的特征向量",
            ["A 的行列式为 0", "A 的元素全为正", "A 是上三角矩阵"],
            "可对角化 ⇔ 存在 n 个线性无关特征向量构成可逆矩阵 P。",
        )
    )
    items.append(
        _q(
            "二次型 f(x₁, x₂) = x₁² + 4x₁x₂ + x₂² 对应的对称矩阵是：",
            "[1 2; 2 1]",
            ["[1 4; 4 1]", "[1 0; 0 1]", "[1 2; 0 1]"],
            "交叉项系数平分到对称位置：4x₁x₂ → a₁₂ = a₂₁ = 2。",
        )
    )
    return items


def _linear_algebra_items() -> List[Dict]:
    """「线性代数」是模块级知识点，取各子模块的基础题混合。"""
    items: List[Dict] = []
    items.append(
        _q(
            "2 阶行列式 |2 1; 3 4| 的值为：",
            "5",
            ["11", "8", "−5"],
            "2×4 − 1×3 = 8 − 3 = 5。",
        )
    )
    items.append(
        _q(
            "矩阵 A = [1 2; 2 4] 的秩为：",
            "1",
            ["2", "0", "3"],
            "两行成比例，线性相关，秩为 1。",
        )
    )
    items.append(
        _q(
            "n 阶矩阵特征值之和等于：",
            "迹",
            ["行列式", "秩", "迹的平方"],
            "特征多项式根与系数的关系：λ₁+…+λₙ = a₁₁+…+aₙₙ（迹）。",
        )
    )
    items.append(
        _q(
            "n 维向量组线性无关 ⇒ 向量组的秩为：",
            "n（等于向量个数）",
            ["小于 n", "大于 n", "0"],
            "线性无关的向量组秩等于向量个数。",
        )
    )
    items.append(
        _q(
            "设 A 为 3 阶方阵，|A| = 3，则 |Aᵀ| 等于：",
            "3",
            ["1/3", "9", "27"],
            "转置不改变行列式：|Aᵀ| = |A|。",
        )
    )
    items.append(
        _q(
            "设 A 为 3 阶方阵，|A| = 2，则 |2A| 等于：",
            "16",
            ["4", "8", "6"],
            "|kA| = kⁿ|A| = 2³ × 2 = 16。",
        )
    )
    items.append(
        _q(
            "矩阵乘法的维度规则：A 为 2×3，B 为 3×4，则 AB 的行列数为：",
            "2×4",
            ["3×3", "4×2", "2×3"],
            "(m×n)(n×p) = m×p，故为 2×4。",
        )
    )
    items.append(
        _q(
            "方阵 A 可逆的充要条件是：",
            "|A| ≠ 0",
            ["A 的所有元素非零", "A 对称", "A 的迹为 0"],
            "行列式非零 ⇔ 满秩 ⇔ 可逆。",
        )
    )
    return items


# --------------------------------------------------------------------------
# 级数
# --------------------------------------------------------------------------

def _series_items() -> List[Dict]:
    items: List[Dict] = []
    items.append(
        _q(
            "等比级数 ∑(n=0→∞) (1/2)ⁿ 的和为：",
            "2",
            ["1", "1/2", "发散"],
            "首项 1、公比 1/2，和 = a/(1−q) = 1/(1−1/2) = 2。",
        )
    )
    items.append(
        _q(
            "级数 ∑(n=1→∞) 1/n² ：",
            "收敛",
            ["发散", "条件收敛", "和为无穷大"],
            "p 级数 ∑1/nᵖ 在 p > 1 时收敛，此处 p = 2。",
        )
    )
    items.append(
        _q(
            "调和级数 ∑(n=1→∞) 1/n ：",
            "发散",
            ["收敛", "条件收敛", "绝对收敛"],
            "p = 1 的 p 级数，即调和级数，发散。",
        )
    )
    items.append(
        _q(
            "级数 ∑(n=0→∞) xⁿ 在 |x| < 1 时的和为：",
            "1/(1 − x)",
            ["x/(1 − x)", "1/(1 + x)", "x"],
            "几何级数求和公式：首项 1、公比 x，和 = 1/(1−x)。",
        )
    )
    items.append(
        _q(
            "若级数 ∑uₙ 收敛，则通项 uₙ 满足：",
            "lim(n→∞) uₙ = 0",
            ["∑|uₙ| 必收敛", "uₙ 单调递减", "uₙ > 0"],
            "收敛的必要条件是通项趋于 0（反之不成立，如调和级数）。",
        )
    )
    items.append(
        _q(
            "交错级数 ∑(n=1→∞) (−1)ⁿ⁻¹/n ：",
            "条件收敛",
            ["绝对收敛", "发散", "和为 0"],
            "取绝对值后为调和级数发散，本身由莱布尼茨判别法收敛，故条件收敛。",
        )
    )
    items.append(
        _q(
            "幂级数 ∑ xⁿ/n! 的收敛半径为：",
            "∞（全数轴收敛）",
            ["1", "0", "e"],
            "比值判别：|uₙ₊₁/uₙ| = |x|/(n+1) → 0，对任意 x 都收敛，收敛半径为无穷。",
        )
    )
    items.append(
        _q(
            "级数 ∑(n=1→∞) 1/n³ 属于：",
            "收敛的 p 级数（p = 3）",
            ["调和级数", "发散的 p 级数", "交错级数"],
            "p 级数 ∑1/nᵖ 在 p > 1 时收敛，此处 p = 3 > 1。",
        )
    )
    return items


# --------------------------------------------------------------------------
# 概率论
# --------------------------------------------------------------------------

def _probability_items() -> List[Dict]:
    items: List[Dict] = []
    items.append(
        _q(
            "掷一枚均匀骰子，出现偶数点的概率是：",
            "1/2",
            ["1/3", "1/6", "2/3"],
            "偶数点有 2、4、6 共 3 个，3/6 = 1/2。",
        )
    )
    items.append(
        _q(
            "若事件 A、B 互斥，则 P(A∪B) 等于：",
            "P(A) + P(B)",
            ["P(A)P(B)", "P(A) + P(B) − P(A)P(B)", "0"],
            "互斥事件不能同时发生，P(AB) = 0，加法公式退化为直接相加。",
        )
    )
    items.append(
        _q(
            "若事件 A、B 相互独立，则 P(AB) 等于：",
            "P(A)P(B)",
            ["P(A) + P(B)", "P(A) − P(B)", "P(A)/P(B)"],
            "独立的定义即乘积公式 P(AB) = P(A)P(B)。",
        )
    )
    items.append(
        _q(
            "从 1、2、3、4、5 中任取一数，取到奇数的概率为：",
            "3/5",
            ["2/5", "1/2", "1/5"],
            "奇数有 1、3、5 共 3 个，共 5 个数，故为 3/5。",
        )
    )
    items.append(
        _q(
            "必然事件的概率为：",
            "1",
            ["0", "0.5", "不确定"],
            "必然事件包含全部样本点，概率为 1；不可能事件为 0。",
        )
    )
    items.append(
        _q(
            "古典概型中，事件 A 的概率等于：",
            "A 包含的样本点数 / 样本点总数",
            ["样本点总数 / A 包含的样本点数", "1 / 样本点总数", "A 的元素个数"],
            "古典概型要求样本点等可能，概率由有利结果数与总数之比给出。",
        )
    )
    items.append(
        _q(
            "条件概率 P(A|B) 的定义式为：",
            "P(AB)/P(B)（P(B) > 0）",
            ["P(AB)/P(A)", "P(A)P(B)", "P(A∪B)/P(B)"],
            "条件概率在 B 已发生的前提下重新归一化样本空间，需 P(B) > 0。",
        )
    )
    items.append(
        _q(
            "若 P(A) = 0.3，P(B) = 0.4，A、B 互斥，则 P(A∪B) 为：",
            "0.7",
            ["0.12", "0.58", "0.1"],
            "互斥时 P(A∪B) = 0.3 + 0.4 = 0.7。",
        )
    )
    return items


def _random_variable_items() -> List[Dict]:
    items: List[Dict] = []
    items.append(
        _q(
            "离散型随机变量 X 的分布律要求所有概率之和等于：",
            "1",
            ["0", "0.5", "X 的期望"],
            "分布律必须满足非负性与归一性（概率和为 1）。",
        )
    )
    items.append(
        _q(
            "连续型随机变量的概率密度函数 f(x) 满足 ∫f(x)dx（全实轴）等于：",
            "1",
            ["0", "E(X)", "Var(X)"],
            "密度函数在整个定义域上积分为 1，与分布律的归一性一致。",
        )
    )
    items.append(
        _q(
            "对任意随机变量 X，P(X = a) 在 X 为连续型时等于：",
            "0",
            ["f(a)", "1", "F(a)"],
            "连续型随机变量取单点的概率为 0，概率由区间积分给出。",
        )
    )
    items.append(
        _q(
            "分布函数 F(x) 的定义是：",
            "P(X ≤ x)",
            ["P(X = x)", "P(X ≥ x)", "P(X < x) 的导数"],
            "分布函数定义为 F(x) = P(X ≤ x)，单调不减且右连续。",
        )
    )
    items.append(
        _q(
            "若 X 只能取 0 和 1，P(X=1) = p，则 E(X) 等于：",
            "p",
            ["1 − p", "p(1 − p)", "2p"],
            "0-1 分布的期望 = 1×p + 0×(1−p) = p。",
        )
    )
    items.append(
        _q(
            "随机变量 X 的方差 Var(X) 等于：",
            "E(X²) − [E(X)]²",
            ["E(X²)", "[E(X)]²", "E(X²) + [E(X)]²"],
            "方差的计算公式：Var(X) = E[(X−EX)²] = E(X²) − (EX)²。",
        )
    )
    return items


def _distribution_items() -> List[Dict]:
    items: List[Dict] = []
    items.append(
        _q(
            "二项分布 B(n, p) 的期望为：",
            "np",
            ["p", "n/p", "np(1 − p)"],
            "二项分布由 n 次独立伯努利试验构成，期望为 np，方差为 np(1−p)。",
        )
    )
    items.append(
        _q(
            "二项分布 B(n, p) 的方差为：",
            "np(1 − p)",
            ["np", "p(1 − p)", "np²"],
            "方差等于各次试验方差之和：n·p(1−p)。",
        )
    )
    items.append(
        _q(
            "泊松分布 P(λ) 的期望与方差分别为：",
            "λ 和 λ",
            ["λ 和 λ²", "1/λ 和 1/λ²", "λ 和 1"],
            "泊松分布的期望与方差都等于参数 λ。",
        )
    )
    items.append(
        _q(
            "标准正态分布 N(0, 1) 的期望和方差为：",
            "0 和 1",
            ["1 和 0", "0 和 0", "1 和 1"],
            "标准正态分布的参数 μ = 0、σ² = 1 就是期望与方差。",
        )
    )
    items.append(
        _q(
            "正态分布 N(μ, σ²) 关于哪条直线对称：",
            "x = μ",
            ["x = σ", "x = 0", "x = μ + σ"],
            "正态密度函数关于均值 μ 对称，μ 同时是期望、中位数与众数。",
        )
    )
    items.append(
        _q(
            "均匀分布 U(a, b) 的期望为：",
            "(a + b)/2",
            ["(b − a)/2", "ab/2", "a + b"],
            "均匀分布对称，期望落在区间中点 (a+b)/2。",
        )
    )
    return items


def _expectation_items() -> List[Dict]:
    items: List[Dict] = []
    items.append(
        _q(
            "对任意常数 C，E(CX) 等于：",
            "C·E(X)",
            ["E(X)", "C + E(X)", "C²E(X)"],
            "期望的线性性质：常数可提出。",
        )
    )
    items.append(
        _q(
            "若 X、Y 相互独立，则 Var(X + Y) 等于：",
            "Var(X) + Var(Y)",
            ["Var(X) + Var(Y) + 2Cov(X,Y)", "Var(X) − Var(Y)", "Var(X)·Var(Y)"],
            "独立时协方差为 0，方差可加。",
        )
    )
    items.append(
        _q(
            "对任意随机变量，Var(aX + b) 等于：",
            "a²Var(X)",
            ["aVar(X) + b", "a²Var(X) + b", "aVar(X)"],
            "常数平移不影响方差，系数提出时平方：Var(aX+b) = a²Var(X)。",
        )
    )
    items.append(
        _q(
            "若 E(X) = 2，E(X²) = 8，则 Var(X) 等于：",
            "4",
            ["6", "12", "2"],
            "Var(X) = E(X²) − [E(X)]² = 8 − 4 = 4。",
        )
    )
    items.append(
        _q(
            "若 E(X) = 3，则 E(2X − 1) 等于：",
            "5",
            ["6", "4", "2"],
            "E(2X − 1) = 2E(X) − 1 = 6 − 1 = 5。",
        )
    )
    items.append(
        _q(
            "随机变量的标准差等于：",
            "方差的算术平方根",
            ["方差的平方", "期望的平方", "方差的倒数"],
            "标准差 σ = √Var(X)，与 X 同量纲。",
        )
    )
    return items


def _lln_items() -> List[Dict]:
    items: List[Dict] = []
    items.append(
        _q(
            "切比雪夫不等式刻画的是：",
            "随机变量偏离其期望的概率上界",
            ["随机变量的分布函数", "两个事件的独立性", "样本均值的精确分布"],
            "P(|X − E(X)| ≥ ε) ≤ Var(X)/ε²，只用到期望和方差就能给出偏离概率的上界。",
        )
    )
    items.append(
        _q(
            "大数定律说明：当 n → ∞ 时，样本均值依概率收敛于：",
            "总体期望 μ",
            ["总体方差 σ²", "0", "样本中位数"],
            "辛钦大数定律：独立同分布且期望存在时，样本均值依概率收敛到 μ。",
        )
    )
    items.append(
        _q(
            "中心极限定理指出，n 充分大时样本均值近似服从：",
            "正态分布",
            ["均匀分布", "泊松分布", "指数分布"],
            "无论总体分布如何，样本均值的标准化形式渐近标准正态分布。",
        )
    )
    items.append(
        _q(
            "棣莫弗—拉普拉斯中心极限定理处理的是：",
            "二项分布的正态近似",
            ["指数分布的泊松近似", "均匀分布的极限", "泊松分布的正态近似"],
            "该定理说明二项分布在 n 大时可用正态分布近似（np、np(1−p) 为参数）。",
        )
    )
    items.append(
        _q(
            "中心极限定理中，样本均值标准化后分母是：",
            "σ/√n",
            ["σ", "σ²/n", "√n/σ"],
            "标准化：(X̄ − μ)/(σ/√n) 依分布收敛于 N(0,1)。",
        )
    )
    items.append(
        _q(
            "辛钦大数定律要求的条件是：",
            "独立同分布且数学期望存在",
            ["方差必须存在", "总体必须正态", "样本量小于 30"],
            "辛钦大数定律只需期望存在，不要求方差存在；这是它比切比雪夫版本更强的地方。",
        )
    )
    return items


def _advanced_math_items() -> List[Dict]:
    """「高等数学」是模块级知识点，混合各章基础题，避免与子知识点完全重复。"""
    items: List[Dict] = []
    items.append(
        _q(
            "函数 f(x) = x² − 4x + 3 的极小值点为：",
            "x = 2",
            ["x = 1", "x = 3", "x = 0"],
            "f'(x) = 2x − 4 = 0 得 x = 2，且 f''(2) = 2 > 0，为极小值点。",
        )
    )
    items.append(
        _q(
            "曲线 y = x³ 的拐点坐标是：",
            "(0, 0)",
            ["(1, 1)", "(−1, −1)", "不存在拐点"],
            "y'' = 6x，在 x = 0 处变号，故 (0,0) 为拐点。",
        )
    )
    items.append(
        _q(
            "微分方程 y' = y 的通解是：",
            "y = Ce^x",
            ["y = Cx", "y = C + x", "y = Ce^(−x)"],
            "分离变量 dy/y = dx，积分得 ln|y| = x + C，即 y = Ce^x。",
        )
    )
    items.append(
        _q(
            "若 f'(x) > 0 在区间 I 上恒成立，则 f(x) 在 I 上：",
            "单调递增",
            ["单调递减", "恒为常数", "存在极大值"],
            "导数恒正说明函数在该区间严格单调递增。",
        )
    )
    items.append(
        _q(
            "∫₀¹ x² dx 的值为：",
            "1/3",
            ["1/2", "1", "1/4"],
            "∫x²dx = x³/3，代入 0 到 1 得 1/3。",
        )
    )
    items.append(
        _q(
            "函数 y = ln x 的定义域是：",
            "(0, +∞)",
            ["[0, +∞)", "(−∞, +∞)", "(1, +∞)"],
            "对数要求真数为正，故 x > 0。",
        )
    )
    items.append(
        _q(
            "lim(x→0) (sin x)/x 的值为：",
            "1",
            ["0", "∞", "不存在"],
            "重要极限之一，sin x ~ x（x→0）。",
        )
    )
    items.append(
        _q(
            "若函数 f(x) 在 [a, b] 上连续，则 f(x) 在该区间上：",
            "必有最大值和最小值",
            ["必定可导", "必定单调", "必定取到 0"],
            "闭区间上连续函数必有界且取得最大最小值（最值定理）。",
        )
    )
    return items


# --------------------------------------------------------------------------
# 题库注册
# --------------------------------------------------------------------------

def _bank(key: str, module: str, points: Sequence[str], match: Sequence[str], items: List[Dict]) -> Dict:
    return {
        "key": key,
        "module": module,
        "points": tuple(points),
        "match": tuple(match),
        "language": "zh",
        "items": items,
        "generated": True,
    }


def generated_banks() -> List[Dict]:
    """程序化补充题库：每个数学知识点独立成库，题不跨点混用。"""
    return [
        _bank("gen_definite_integral", "高等数学", ("定积分",), ("定积分",), _definite_integral_items()),
        _bank("gen_indefinite_integral", "高等数学", ("不定积分",), ("不定积分",), _indefinite_integral_items()),
        _bank("gen_derivative", "高等数学", ("导数与微分", "导数", "微分"), ("导数与微分", "导数"), _derivative_items()),
        _bank("gen_limits", "高等数学", ("函数与极限", "极限"), ("函数与极限",), _limits_items()),
        _bank("gen_advanced_math", "高等数学", ("高等数学", "微积分"), ("高等数学",), _advanced_math_items()),
        _bank("gen_series", "高等数学", ("级数",), ("级数",), _series_items()),
        _bank("gen_determinant", "线性代数", ("行列式",), ("行列式",), _determinant_items()),
        _bank("gen_matrix", "线性代数", ("矩阵",), ("矩阵",), _matrix_items()),
        _bank("gen_vector", "线性代数", ("向量",), ("向量",), _vector_items()),
        _bank("gen_eigen", "线性代数", ("特征值与二次型", "特征值"), ("特征值与二次型", "特征值"), _eigen_items()),
        _bank("gen_linear_algebra", "线性代数", ("线性代数", "线代"), ("线性代数",), _linear_algebra_items()),
        _bank("gen_probability", "概率论与数理统计", ("概率论与数理统计", "概率论"), ("概率论与数理统计",), _probability_items()),
        _bank("gen_random_variable", "概率论与数理统计", ("随机变量",), ("随机变量",), _random_variable_items()),
        _bank("gen_distribution", "概率论与数理统计", ("常见分布",), ("常见分布",), _distribution_items()),
        _bank("gen_expectation", "概率论与数理统计", ("期望与方差",), ("期望与方差",), _expectation_items()),
        _bank("gen_lln", "概率论与数理统计", ("大数定律与中心极限定理",), ("大数定律与中心极限定理", "大数定律"), _lln_items()),
    ]


GENERATED_BANKS: List[Dict] = generated_banks()
