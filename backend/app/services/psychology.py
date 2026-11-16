"""心理评估模块：真实公开量表计分 + DeepSeek 解读 + 外部知识库证据 + 公开援助资源。

量表题目与计分规则来自公开的标准自评量表；结果解读由真实模型生成，失败时用规则文案。
本模块只做自我觉察，不提供医学诊断。
"""

import time
from typing import Dict, List, Optional

from ..cache import cache
from ..llm import llm
from . import knowledge_base

OPTIONS_4 = [
    {"value": 0, "label": "完全不会"},
    {"value": 1, "label": "好几天"},
    {"value": 2, "label": "一半以上的天数"},
    {"value": 3, "label": "几乎每天"},
]

OPTIONS_5 = [
    {"value": 0, "label": "从不"},
    {"value": 1, "label": "很少"},
    {"value": 2, "label": "有时"},
    {"value": 3, "label": "经常"},
    {"value": 4, "label": "总是"},
]

SCALES: List[Dict] = [
    {
        "key": "phq9",
        "name": "PHQ-9 情绪自评",
        "intro": "过去两周内，以下问题困扰你的频率。用于自我觉察，不替代专业诊断。",
        "options": OPTIONS_4,
        "max_score": 27,
        "levels": [
            {"max": 4, "label": "无明显抑郁症状", "tone": "good"},
            {"max": 9, "label": "轻度", "tone": "mild"},
            {"max": 14, "label": "中度", "tone": "medium"},
            {"max": 19, "label": "中重度", "tone": "high"},
            {"max": 27, "label": "重度", "tone": "high"},
        ],
        "questions": [
            "做事时提不起劲或没有兴趣",
            "感到心情低落、沮丧或绝望",
            "入睡困难、睡不安稳或睡眠过多",
            "感觉疲倦或没有活力",
            "食欲不振或吃太多",
            "觉得自己很糟，或觉得自己很失败",
            "对事情专注有困难，例如阅读或看视频",
            "动作或说话缓慢，或烦躁不安、动来动去",
            "有不如死掉或伤害自己的念头",
        ],
        "source": "PHQ-9（公开筛查量表）",
    },
    {
        "key": "gad7",
        "name": "GAD-7 焦虑自评",
        "intro": "过去两周内，以下焦虑相关感受出现的频率。",
        "options": OPTIONS_4,
        "max_score": 21,
        "levels": [
            {"max": 4, "label": "无明显焦虑症状", "tone": "good"},
            {"max": 9, "label": "轻度", "tone": "mild"},
            {"max": 14, "label": "中度", "tone": "medium"},
            {"max": 21, "label": "重度", "tone": "high"},
        ],
        "questions": [
            "感到紧张、焦虑或急切",
            "无法停止或控制担忧",
            "对各种各样的事情担忧过多",
            "很难放松下来",
            "由于不安而无法静坐",
            "变得容易烦恼或急躁",
            "感到似乎将有可怕的事情发生而害怕",
        ],
        "source": "GAD-7（公开筛查量表）",
    },
    {
        "key": "pss10",
        "name": "PSS-10 压力自评",
        "intro": "过去一个月，你的感受与想法出现的频率。其中 4 题为反向计分。",
        "options": OPTIONS_5,
        "max_score": 40,
        "reverse": [3, 4, 6, 7],
        "levels": [
            {"max": 13, "label": "感知压力较低", "tone": "good"},
            {"max": 26, "label": "感知压力中等", "tone": "medium"},
            {"max": 40, "label": "感知压力较高", "tone": "high"},
        ],
        "questions": [
            "因为发生意外的事情而感到心烦",
            "感到无法控制生活中重要的事情",
            "感到紧张和压力大",
            "有信心处理个人问题",
            "觉得事情正按照自己的意愿发展",
            "发现无法应付所有必须做的事情",
            "能够控制生活中令人烦恼的事情",
            "觉得能够掌控自己的时间安排",
            "因为超出控制的事情而生气",
            "感到困难堆积如山无法克服",
        ],
        "source": "PSS-10（公开压力量表）",
    },
]

SCALE_MAP = {item["key"]: item for item in SCALES}

RESOURCES = [
    {
        "name": "全国统一心理援助热线",
        "contact": "12356",
        "note": "国家卫生健康委开通，24 小时免费心理支持（公开信息，请以官方为准）",
    },
    {
        "name": "北京心理危机研究与干预中心",
        "contact": "010-82951332",
        "note": "24 小时危机干预热线（公开信息）",
    },
    {
        "name": "教育部华中师范大学心理援助热线",
        "contact": "4009678920",
        "note": "面向学生与家长（公开信息）",
    },
]


def scale_list() -> List[Dict]:
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "intro": item["intro"],
            "question_count": len(item["questions"]),
            "max_score": item["max_score"],
            "source": item["source"],
        }
        for item in SCALES
    ]


def get_scale(key: str) -> Optional[Dict]:
    return SCALE_MAP.get(key)


def _level(scale: Dict, score: int) -> Dict:
    for level in scale["levels"]:
        if score <= level["max"]:
            return level
    return scale["levels"][-1]


def _reverse_score(scale: Dict, index: int, value: int) -> int:
    if index in scale.get("reverse", []):
        return 4 - value
    return value


def _rule_interpretation(scale: Dict, score: int, level: Dict, answers: List[int]) -> str:
    total = len(scale["questions"])
    peak = max(range(total), key=lambda i: answers[i]) if answers else 0
    peak_question = scale["questions"][peak] if answers else ""
    base = (
        f"本次{scale['name']}得分 {score} / {scale['max_score']}，对应「{level['label']}」。"
        f"最突出的感受是「{peak_question}」。"
    )
    if level["tone"] == "good":
        return base + "当前状态整体平稳，保持规律作息和适度运动即可。"
    if level["tone"] == "mild":
        return base + "建议先把学习任务颗粒度调小，保证睡眠，并安排每天 20 分钟的活动或散步。"
    return base + "建议尽快与信任的人沟通，并联系学校心理中心或拨打公开心理援助热线进一步评估。"


async def _external_evidence(scale: Dict) -> Dict:
    term = "考试焦虑" if scale["key"] != "pss10" else "心理压力"
    try:
        data = await knowledge_base.lookup(term)
    except Exception:
        return {"available": False, "sources": []}
    sources = [
        {"name": item["name"], "summary": item["summary"], "link": item["link"]}
        for item in data.get("sources", [])
        if item.get("status") == "ok" and item.get("summary")
    ]
    return {"available": bool(sources), "sources": sources}


async def assess(scale_key: str, answers: List[int]) -> Dict:
    scale = SCALE_MAP.get(scale_key)
    if not scale:
        raise ValueError("未知的量表")

    total = len(scale["questions"])
    if len(answers) != total:
        raise ValueError(f"需要 {total} 道题的答案")

    scored = []
    for index, value in enumerate(answers):
        value = int(value)
        if value < 0 or value > scale["options"][-1]["value"]:
            raise ValueError("答案超出选项范围")
        scored.append(_reverse_score(scale, index, value))

    score = sum(scored)
    level = _level(scale, score)

    key = f"psy:{scale_key}:{score}:{hash(tuple(scored)) & 0xffffffff}"
    cached = cache.get_json(key)
    if cached and cached.get("evidence") is not None:
        cached["cached"] = True
        return cached

    evidence = await _external_evidence(scale)
    interpretation = _rule_interpretation(scale, score, level, answers)
    engine = "rule"
    if llm.available:
        system = (
            "你是学校心理中心的科普助手。请基于自评量表结果写一段 150 字以内的解读，"
            "语气温和、非诊断、给出 2-3 条可执行建议；不要编造分数；只输出中文正文。"
        )
        prompt = (
            f"量表：{scale['name']}；得分：{score}/{scale['max_score']}；分级：{level['label']}；"
            f"各题答案：{answers}；规则参考：{interpretation}"
        )
        text = await llm.chat(system, prompt, temperature=0.4, max_tokens=400)
        if text:
            interpretation = text.strip()
            engine = "llm"

    safety = {
        "urgent": False,
        "message": "",
    }
    if scale_key == "phq9" and answers and answers[8] > 0:
        safety = {
            "urgent": True,
            "message": "检测到与自伤相关的回答。请立即联系信任的人或拨打 12356，必要时前往医院心理科。",
        }

    result = {
        "scale": scale_key,
        "scale_name": scale["name"],
        "score": score,
        "max_score": scale["max_score"],
        "level": level["label"],
        "tone": level["tone"],
        "interpretation": {"text": interpretation, "engine": engine},
        "evidence": evidence,
        "safety": safety,
        "resources": RESOURCES,
        "source": scale["source"],
        "answered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False,
    }
    cache.set_json(key, result, ttl=600)
    return result