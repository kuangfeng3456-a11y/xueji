"""按知识点分类的内置题库。

用途：随堂测 / 探针优先从对应题库取题，题库没有覆盖时再让模型补题。
好处：离线可用、题型稳定、不会把高数题出成英文；也方便按知识点核对答案。

匹配规则（按优先级）：
1. 精确知识点名命中 `points` —— 一个知识点一个题库，矩阵不会拿到行列式的题；
2. 关键词命中，且关键词越长优先级越高 —— 「大数定律与中心极限定理」优先命中
   「大数定律」而不是「极限」，不会再被误判成高数题；
3. 都没有命中时返回 None，交由在线题库（模型生成 + 缓存）补题。
"""

from typing import Dict, List, Optional

from .qbank_english import ENGLISH_BANKS
from .qbank_english_extended import ENGLISH_BANKS_EXTENDED
from .qbank_generated import GENERATED_BANKS
from .qbank_math import MATH_BANKS
from .qbank_math_extended import MATH_BANKS_EXTENDED


def _merge_generated(banks: List[Dict]) -> List[Dict]:
    """把程序化题源合并进同知识点的题库。

    每个知识点原库只有 4 题，连续做几次就重复；程序化题由公式算出答案，
    可直接并入原库（而不是另建一个同名库——那样永远匹配不到，会被原库挡住）。

    合并时按「全局题干」去重：同一道题不能同时出现在两个库里，
    否则「矩阵」的测验可能抽到「行列式」的同一道题，考点就串了。
    找不到对应知识点的程序化库直接追加为新库。
    """
    seen_questions = {
        item["question"] for bank in banks for item in (bank.get("items") or [])
    }
    for extra in GENERATED_BANKS:
        target: Optional[Dict] = None
        for bank in banks:
            if set(extra["points"]) & set(bank["points"]):
                target = bank
                break
        if target is None:
            banks.append(extra)
            target = extra
        for item in extra["items"]:
            if item["question"] in seen_questions:
                continue
            target["items"].append(item)
            seen_questions.add(item["question"])
    return banks


# ============================================================================
# 题库总集：英语 30 库 + 数学 30 库 + 程序化补充（每知识点 8~12 题）
# ============================================================================
BANKS: List[Dict] = _merge_generated(
    ENGLISH_BANKS + ENGLISH_BANKS_EXTENDED + MATH_BANKS + MATH_BANKS_EXTENDED
)

# 过于宽泛的关键词：只允许「完全相等 / 以它开头」，避免「波函数」被当成「函数」
GENERIC_KEYWORDS = {"函数", "数学"}

# 题库来源标签（前端展示用）
SOURCE_LOCAL = "内置题库"
SOURCE_MODULE = "模块题库"
SOURCE_EXTERNAL = "外部题库 API"
SOURCE_ONLINE = "模型生成（非真题库）"


def _keyword_hit(name: str, keyword: str) -> bool:
    if name == keyword or name.startswith(keyword):
        return True
    if keyword in GENERIC_KEYWORDS:
        return False
    return keyword in name


def _match_bank(kp_name: str, language: Optional[str] = None) -> Optional[Dict]:
    name = (kp_name or "").strip()
    if not name:
        return None

    def _allowed(bank: Dict) -> bool:
        # 学科隔离：中文知识点不得命中英文词汇库，反之亦然。
        # 否则「概念辨析」会因为含「辨析」二字被当成英语近义词题。
        if not language:
            return True
        return (bank.get("language") or "zh") == language

    # 1. 精确名优先：题库自己声明的知识点名
    for bank in BANKS:
        if _allowed(bank) and name in bank["points"]:
            return bank
    # 2. 关键词兜底：命中的关键词越长越具体
    best: Optional[Dict] = None
    best_len = 0
    for bank in BANKS:
        if not _allowed(bank):
            continue
        for keyword in bank["match"]:
            if not _keyword_hit(name, keyword):
                continue
            if len(keyword) > best_len:
                best, best_len = bank, len(keyword)
    return best


def bank_of(kp_name: str, language: Optional[str] = None) -> Dict:
    """返回知识点对应题库的描述（不含题目），未覆盖时返回空字典。

    language 传入 "zh"/"en" 时按学科隔离，避免中英题库互相串题。
    """
    bank = _match_bank(kp_name, language)
    if not bank:
        return {}
    return {
        "key": bank["key"],
        "module": bank.get("module", ""),
        "language": bank.get("language", "zh"),
        "size": len(bank["items"]),
        "source": SOURCE_LOCAL,
    }


def pick(
    kp_name: str, limit: int = 2, offset: int = 0, language: Optional[str] = None
) -> List[Dict]:
    """取该知识点对应的题库题目（深拷贝，避免调用方改到原始数据）。

    offset 用于轮换：同一知识点连续出题时从不同位置开始，减少重复。
    limit 大于题库容量时只返回题库全部题目，不会重复凑数。
    language 用于学科隔离，见 ``bank_of``。
    """
    bank = _match_bank(kp_name, language)
    if not bank:
        return []
    return _pick_from_bank(bank, limit, offset)


def _pick_from_bank(bank: Dict, limit: int = 2, offset: int = 0) -> List[Dict]:
    items = bank.get("items") or []
    if not items:
        return []
    limit = max(0, int(limit))
    start = int(offset) % len(items)
    ordered = items[start:] + items[:start]
    picked: List[Dict] = []
    for item in ordered[:limit]:
        answer_index = item["answer_index"]
        picked.append(
            {
                "question": item["question"],
                "options": list(item["options"]),
                "answer_index": answer_index,
                "explanation": item["explanation"],
                "option_reasons": [
                    "" if index == answer_index else "常见错误" for index in range(4)
                ],
                "distractor_causes": [
                    None if index == answer_index else "concept" for index in range(4)
                ],
                "source": SOURCE_LOCAL,
                "bank_key": bank["key"],
                "module": bank.get("module", ""),
            }
        )
    return picked


def banks() -> List[Dict]:
    """全部题库（只读，供同模块补题使用）。"""
    return BANKS


def pick_by_key(bank_key: str, limit: int = 4, offset: int = 0) -> List[Dict]:
    """按题库 key 直接取题（同模块补题用，不经过知识点匹配）。"""
    for bank in BANKS:
        if bank["key"] == bank_key:
            return _pick_from_bank(bank, limit, offset)
    return []


def point_names() -> List[str]:
    """题库已精确覆盖的知识点名（用于自检与文档核对）。"""
    names: List[str] = []
    for bank in BANKS:
        names.extend(bank["points"])
    return names


def coverage(point_names_) -> Dict:
    """统计知识点被题库覆盖的情况。"""
    covered = 0
    uncovered: List[str] = []
    names = [name for name in point_names_ if name]
    for name in names:
        if _match_bank(name):
            covered += 1
        else:
            uncovered.append(name)
    return {
        "total": len(names),
        "covered": covered,
        "uncovered": uncovered,
        "rate": round(covered / len(names), 3) if names else 0.0,
    }
