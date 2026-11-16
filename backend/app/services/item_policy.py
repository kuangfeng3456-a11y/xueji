"""出题学科策略：按「知识点所属学科」决定题目语言与题型。

背景：
- 早期只给知识点名称，模型会出「以下哪项最符合‘言外之意’的理解方式」这类元问题；
- 后来按考试统一判语言，又导致 CET-4 目标下的「高等数学」也被迫出英文题。

现在的规则：**语言跟着知识点走**。同一个目标里可以既有英语类知识点（听力/阅读/词汇）
用英文出题，也有数学类知识点（极限/积分/线代/概率）用中文出题。
"""

import re
from typing import Iterable, List, Optional, Tuple

META_PATTERNS = [
    r"属于下列哪个",
    r"属于哪个(学习)?模块",
    r"最需要先确认",
    r"最符合.{0,12}理解方式",
    r"学习策略",
    r"以下哪项.{0,10}方法",
    r"哪一项.{0,8}学习",
    r"应试技巧",
    r"复习方法",
]

# 考试名里出现这些词，说明目标是英语考试
ENGLISH_EXAM_HINTS = ("英语", "四级", "六级", "CET", "考研英语", "雅思", "托福", "IELTS", "TOEFL")

# 知识点属于英语语言类（用英文出题）
ENGLISH_KP_HINTS = (
    "听力",
    "短对话",
    "长对话",
    "听力篇章",
    "阅读",
    "仔细阅读",
    "长篇阅读",
    "选词填空",
    "完形",
    "词汇",
    "高频词汇",
    "熟词僻义",
    "语法",
    "从句",
    "时态",
    "非谓语",
    "句子结构",
    "写作",
    "作文",
    "议论文",
    "常用句型",
    "翻译",
    "英语",
)

# 知识点属于数学 / 理科类（用中文出题）
SCIENCE_KP_HINTS = (
    "数学",
    "高数",
    "高等数学",
    "极限",
    "函数",
    "导数",
    "微分",
    "积分",
    "级数",
    "向量",
    "矩阵",
    "行列式",
    "线性",
    "概率",
    "统计",
    "随机",
    "期望",
    "方差",
    "分布",
    "特征值",
    "二次型",
    "几何",
    "物理",
    "化学",
    "数据结构",
    "算法",
    "计算机网络",
    "操作系统",
)

CJK = re.compile(r"[\u4e00-\u9fff]")
ASCII_WORD = re.compile(r"[A-Za-z]{2,}")


def is_meta_question(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return True
    return any(re.search(pattern, content) for pattern in META_PATTERNS)


def looks_english(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    if not ASCII_WORD.search(content):
        return False
    cjk = len(CJK.findall(content))
    return cjk / max(len(content), 1) <= 0.35


def exam_is_english(exam_name: str) -> bool:
    exam = (exam_name or "").strip()
    return any(hint.lower() in exam.lower() for hint in ENGLISH_EXAM_HINTS)


def language_for_point(exam_name: str, kp_name: str) -> str:
    """返回该知识点出题应使用的语言：'en' 或 'zh'。"""
    name = (kp_name or "").strip()
    if name and any(hint in name for hint in SCIENCE_KP_HINTS):
        return "zh"
    if name and any(hint in name for hint in ENGLISH_KP_HINTS):
        return "en"
    if not exam_is_english(exam_name):
        return "zh"
    # 英语考试里无法判断的知识点：名称是英文才用英文，否则按中文处理
    return "en" if looks_english(name) else "zh"


def _language_plan(exam_name: str, point_names: Iterable[str]) -> List[Tuple[str, str]]:
    plan: List[Tuple[str, str]] = []
    for name in point_names:
        if not name:
            continue
        plan.append((name, language_for_point(exam_name, name)))
    return plan


def subject_policy(exam_name: str, point_names: Iterable[str], mode: str = "quiz") -> str:
    """把「每个知识点用什么语言、什么题型」写进提示词（P05 的 L4 补充层）。"""
    plan = _language_plan(exam_name, point_names)
    english_names = [name for name, lang in plan if lang == "en"]
    chinese_names = [name for name, lang in plan if lang == "zh"]
    lines = [
        "<subject_policy>",
        f"考试：{exam_name or '未指定'}；出题模式：{mode}。",
        "题目必须考学科内容本身，禁止考“学习方法/模块归属/理解方式/复习策略”这类元问题。",
    ]
    if english_names:
        lines.append(
            "英语类知识点（" + "、".join(english_names) + "）：题干与选项一律使用英文（解析可中文）；"
            "听力要给真实对话或独白片段，阅读要给英文句子/段落，词汇考具体词义或搭配。"
        )
    if chinese_names:
        lines.append(
            "中文类知识点（" + "、".join(chinese_names) + "）：题干、选项、解析一律使用中文；"
            "数学题要给出可计算的数值或表达式，公式用纯文本（如 lim(x→0) sin x / x），不要用英文叙述。"
        )
    if not plan:
        lines.append("用该学科的标准题型与术语，选项同质、唯一正确答案、无歧义。")
    lines.append("</subject_policy>")
    return "\n".join(lines)


def item_issues(
    question: str,
    options: Optional[List[str]],
    exam_name: str,
    point_names: Iterable[str],
    kp_name: Optional[str] = None,
) -> List[str]:
    """校验一道题是否符合该知识点的学科策略。"""
    issues: List[str] = []
    if is_meta_question(question):
        issues.append("题干是元问题，不是学科题目")
    names = [name for name in point_names if name]
    target = kp_name or (names[0] if names else "")
    language = language_for_point(exam_name, target)
    option_list = [option for option in (options or []) if isinstance(option, str)]
    if language == "en":
        if not looks_english(question):
            issues.append("英语类知识点题干必须使用英文")
        if option_list and sum(1 for option in option_list if looks_english(option)) < 3:
            issues.append("英语类知识点选项至少 3 个使用英文")
    else:
        if not CJK.search(question):
            issues.append("中文类知识点题干必须使用中文")
    if options is not None and len(options) != 4:
        issues.append("选项数量必须为 4")
    return issues
