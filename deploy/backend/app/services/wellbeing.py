"""心理数据隔离与危机转介（E2）：非诊断、规则分级、12356 与学校心理中心指引。"""

from typing import Dict, List

CRISIS_KEYWORDS = [
    "自杀",
    "不想活",
    "结束生命",
    "活着没意思",
    "自残",
    "伤害自己",
    "轻生",
]
RISK_KEYWORDS = ["绝望", "崩溃", "撑不住", "失眠", "焦虑", "抑郁"]
RESOURCES = [
    {"name": "全国心理援助热线", "contact": "12356", "note": "24 小时，免费"},
    {"name": "学校心理健康中心", "contact": "校医院/心理咨询中心", "note": "可预约面询"},
    {"name": "紧急情况", "contact": "120 / 110", "note": "有立即危险时优先拨打"},
]


def crisis_check(text: str) -> Dict:
    content = (text or "").strip()
    hits = [word for word in CRISIS_KEYWORDS if word in content]
    warnings = [word for word in RISK_KEYWORDS if word in content]
    if hits:
        level = "crisis"
        message = "检测到可能的危机信号。请优先联系专业人员，你并不需要独自承受。"
    elif len(warnings) >= 2:
        level = "elevated"
        message = "近期压力信号较多，建议与信任的人聊聊，或预约学校心理中心。"
    elif warnings:
        level = "watch"
        message = "有一些压力信号，可以先做一次短暂休息与呼吸练习。"
    else:
        level = "normal"
        message = "未检测到明显危机信号。本结果不是诊断，仅供自我关怀参考。"
    return {
        "level": level,
        "message": message,
        "matched_keywords": hits + warnings,
        "resources": RESOURCES if level in ("crisis", "elevated") else RESOURCES[:1],
        "non_diagnostic": True,
        "isolated_from_learning": True,
        "version": "wellbeing-rule-v1",
    }


def referral() -> List[Dict]:
    return RESOURCES