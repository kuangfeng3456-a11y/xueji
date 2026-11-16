"""材料型题目：阅读理解（篇章 + 多题）与听力理解（音频 + 题干）。

普通单选题是「一句话题干 + 四个选项」，用来考英语阅读/听力并不成立：
- 阅读真题是「一篇完整文章 + 若干道针对文章的题」；
- 听力真题是「先听音频，再回答题干」，原文不能提前看到。

这里按知识点类型判断该出哪种材料题，并让同一次出题的若干小题共享同一份材料。
材料仍然由模型实时生成（走真实网络接口），校验不过就返回空，由上层回落到普通题。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..models import KnowledgePoint

# 听力类：必须先听音频
LISTENING_HINTS = (
    "听力",
    "短对话",
    "长对话",
    "听力篇章",
    "听写",
    "听辨",
)

# 阅读类：必须给完整文章
PASSAGE_HINTS = (
    "阅读",
    "仔细阅读",
    "长篇阅读",
    "深度阅读",
    "篇章阅读",
    "选词填空",
)

# 材料长度下限（词）
MIN_PASSAGE_WORDS = 150
MIN_LISTENING_WORDS = 80


def material_kind(point_names: List[str], exam_name: str) -> Optional[str]:
    """判断这组知识点该出哪种材料题；不属于材料题型返回 None。

    只对英语类考试生效——数学题的「阅读材料」是另一套语义，不在这里处理。
    """
    names = [name or "" for name in point_names]
    if not names:
        return None
    if not any(
        hint in name
        for name in names
        for hint in PASSAGE_HINTS + LISTENING_HINTS
    ):
        return None
    listening = sum(1 for name in names if any(h in name for h in LISTENING_HINTS))
    passage = sum(1 for name in names if any(h in name for h in PASSAGE_HINTS))
    if listening and not passage:
        return "listening"
    if passage and not listening:
        return "passage"
    # 混合（同时选了听力和阅读）：按题量更多的那类走，避免两种材料混在一次随堂测里
    return "listening" if listening > passage else "passage"


def system_prompt(kind: str) -> str:
    if kind == "listening":
        return (
            "你是大学英语四级命题老师，负责出一道听力理解题组。输出 JSON："
            '{"material":{"title":"短标题","audio_script":"听力原文（英文对话或短文）"},'
            '"questions":[{"question":"英文题干","options":["A","B","C","D"],'
            '"answer_index":0,"explanation":"中文解析，不超过40字","kp_name":"知识点名称",'
            '"option_reasons":["","典型误解","典型误解","典型误解"],'
            '"distractor_causes":[null,"concept","method","careless"]}]}。'
            "要求：audio_script 是一段真实的英语听力材料（短对话 2-3 轮，或 100-180 词短文），"
            "语言自然、有具体细节（时间、地点、数字、态度），必须写成可直接朗读的连续文本，"
            "不要写说话人标签以外的任何说明，不要出现中文；"
            "questions 要考听力理解（主旨、细节、推断、说话人态度），"
            "题干只描述问题本身，绝不能把听力原文抄进题干或选项；"
            "每题恰好 4 个选项、只有一个正确答案，干扰项必须是听力中容易混淆的信息；"
            "kp_name 必须来自给定知识点。只输出 JSON。"
        )
    return (
        "你是大学英语四级命题老师，负责出一道阅读理解题组。输出 JSON："
        '{"material":{"title":"英文标题","content":"英文文章正文"},'
        '"questions":[{"question":"英文题干","options":["A","B","C","D"],'
        '"answer_index":0,"explanation":"中文解析，不超过40字","kp_name":"知识点名称",'
        '"option_reasons":["","典型误解","典型误解","典型误解"],'
        '"distractor_causes":[null,"concept","method","careless"]}]}。'
        "要求：content 是一篇 180-260 词的完整英语文章，3-4 段，有明确主旨与具体细节，"
        "话题贴近四级真题（社会、科技、教育、健康、环境等），语言地道、不要出现中文；"
        "questions 必须针对这篇文章提问，覆盖主旨、细节、推断、词义四类，"
        "题干和选项都是英文；每题恰好 4 个选项、只有一个正确答案；"
        "kp_name 必须来自给定知识点。只输出 JSON。"
    )


def user_prompt(kind: str, names: List[str], count: int, policy: str) -> str:
    label = "听力材料" if kind == "listening" else "阅读文章"
    return (
        f"知识点：{'、'.join(names)}。\n"
        f"请生成 1 份{label}，并基于它出 {count} 道题。\n"
        f"{policy}"
    )


def parse_material(raw: object, kind: str) -> Optional[Dict]:
    """校验并规整材料；不合格返回 None（上层回落到普通题）。"""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()[:120]
    if kind == "listening":
        script = str(raw.get("audio_script") or raw.get("content") or "").strip()
        words = len(script.split())
        if words < MIN_LISTENING_WORDS:
            return None
        return {
            "kind": "listening",
            "title": title or "Listening Comprehension",
            "audio_script": script[:4000],
            "word_count": words,
        }
    content = str(raw.get("content") or "").strip()
    words = len(content.split())
    if words < MIN_PASSAGE_WORDS:
        return None
    return {
        "kind": "passage",
        "title": title or "Reading Comprehension",
        "content": content[:6000],
        "word_count": words,
    }


def public_material(material: Optional[Dict]) -> Optional[Dict]:
    """给前端的材料视图。

    听力材料不给可直接展示的原文段落，只给朗读脚本与词数；
    原文在交卷后随解析一起返回，避免"先读原文再当听力做"。
    """
    if not material:
        return None
    if material.get("kind") == "listening":
        return {
            "id": material.get("id"),
            "kind": "listening",
            "title": material.get("title"),
            "audio_script": material.get("audio_script"),
            "word_count": material.get("word_count"),
        }
    return {
        "id": material.get("id"),
        "kind": "passage",
        "title": material.get("title"),
        "content": material.get("content"),
        "word_count": material.get("word_count"),
    }
