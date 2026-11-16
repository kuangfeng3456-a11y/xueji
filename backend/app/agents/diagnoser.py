from typing import Optional, Tuple

from ..llm import llm
from ..services.rules import MISTAKE_CATEGORIES, classify_mistake

VALID_CATEGORIES = tuple(MISTAKE_CATEGORIES.keys())


def _normalize_category(raw: str) -> Optional[str]:
    mapping = {
        "概念不清": "concept",
        "概念": "concept",
        "concept": "concept",
        "方法不会": "method",
        "方法": "method",
        "method": "method",
        "粗心": "careless",
        "careless": "careless",
        "时间不够": "time",
        "时间": "time",
        "time": "time",
    }
    return mapping.get(str(raw).strip().lower() if str(raw).strip().isascii() else str(raw).strip())


async def diagnose(
    question: str,
    user_answer: str,
    correct_answer: str,
    kp_name: Optional[str] = None,
) -> Tuple[str, str, str, str]:
    """返回 (category, label, suggestion, engine)。

    优先调用大模型做语义归因，输出必须落在四类枚举内；否则回退规则引擎。
    """
    category, label, suggestion = classify_mistake(question, user_answer, correct_answer)

    if llm.available:
        system = (
            "你是错题归因助手。只能把错因归为以下四类之一："
            "concept=概念不清，method=方法不会，careless=粗心，time=时间不够。"
            '输出 JSON：{"category":"concept|method|careless|time","suggestion":"一句可执行的补救建议"}。'
            "不要输出其它内容。"
        )
        prompt = (
            f"知识点：{kp_name or '未指定'}\n题目：{question}\n"
            f"学生答案：{user_answer or '未作答'}\n正确答案：{correct_answer or '未提供'}"
        )
        data = await llm.chat_json(system, prompt)
        if isinstance(data, dict):
            normalized = _normalize_category(data.get("category", ""))
            suggestion_text = str(data.get("suggestion", "")).strip()
            if normalized in VALID_CATEGORIES and suggestion_text:
                return normalized, MISTAKE_CATEGORIES[normalized], suggestion_text[:300], "llm"

    return category, label, suggestion, "rule"