"""备考方案：把「我要备考」变成一份可执行的网课式课表。

对应文档 v2.0 的目标：项目要给出**全套方案**——第一天上午、下午、晚上分别干什么，
每个时段挂上对应的知识网络、真实视频课程与随堂测，每个阶段都要有一次考试。

三条硬约束（与本项目其它模块一致）：
1. **判定与排期不经过模型**：阶段划分、时段分配、知识点选取、测试卷生成全部走规则；
2. **内容走真实网络接口**：视频课程来自 B 站公开搜索接口，题目来自统一出题官；
3. **不造假数据**：视频搜不到就显示「暂不可用」，不塞内置示例视频。
"""

import json
from datetime import date, datetime, timedelta
import asyncio
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    ExamPrepDay,
    ExamPrepStage,
    Goal,
    KnowledgePoint,
    Mastery,
    Mistake,
    User,
)
from . import advanced, item_policy, knowledge_graph, knowledge_map, video_search
from .learning_events import record_event

# 一天的三个时段：像网课一样，上午学新课、下午练题、晚上复盘
SLOTS = [
    {
        "slot": "morning",
        "label": "上午",
        "range": "08:30 - 11:30",
        "role": "new",
        "icon": "☀",
    },
    {
        "slot": "afternoon",
        "label": "下午",
        "range": "14:00 - 17:00",
        "role": "practice",
        "icon": "◐",
    },
    {
        "slot": "evening",
        "label": "晚上",
        "range": "19:00 - 22:00",
        "role": "review",
        "icon": "☾",
    },
]

ROLE_LABELS = {"new": "学新课", "practice": "练题", "review": "复习巩固"}
# 阶段考试安排在最后一个学习日的晚上
STAGE_EXAM_TITLE = "阶段模考"
# 视频检索用的学科关键词前缀（按考试名推断，避免跨学科搜到无关课程）
VIDEO_PREFIX = {
    "考研": "考研",
    "四级": "四级",
    "六级": "六级",
    "数学": "数学",
    "华为": "华为 HCIA",
}


def _search_prefix(exam_name: str) -> str:
    """检索视频时用的学科前缀。

    B 站课程标题普遍带学科词（「英语句子成分」「四级听力」），
    光用知识点名容易搜不到（实测「句子结构」0 结果、「英语 句子结构」3 结果）。
    英语类考试统一冠以「英语」，数理工科冠以考试本身的关键字。
    """
    exam = exam_name or ""
    if item_policy.exam_is_english(exam):
        return "英语"
    for key, prefix in VIDEO_PREFIX.items():
        if key in exam:
            return prefix
    return ""


# 视频标题匹配用的通用修饰词：这些词出现在知识点名里但不具备区分度，
# 提取核心词时替换为分隔符丢弃（「不定积分概念与性质」→「不定积分」）。
_VIDEO_GENERIC_WORDS = (
    "概念", "性质", "基础", "入门", "方法", "技巧", "初步", "概述",
    "及其", "应用", "专题", "两个", "的", "与", "和", "及其应用",
)


def _kp_tokens(name: str) -> List[str]:
    """从知识点名提取用于视频标题匹配的核心词。

    「不定积分概念与性质」→ [不定积分]；「两个重要极限」→ [重要极限]；
    「导数与微分」→ [导数, 微分]。核心词是标题必须命中的锚，
    这样「隐函数求极值」这类泛热门视频就混不进「两个重要极限」的时段。
    """
    text = str(name or "").strip()
    if not text:
        return []
    for word in _VIDEO_GENERIC_WORDS:
        text = text.replace(word, "|")
    tokens = [piece.strip() for piece in text.split("|") if len(piece.strip()) >= 3]
    return tokens or [str(name).strip()]


def _video_relevance(item: Dict, token_map: Dict[str, List[str]]) -> str:
    """判断一条视频与时段内哪个知识点匹配，返回知识点名（不匹配返回空）。

    优先按视频实际命中的检索词反查知识点（关键词级匹配，最严格）；
    未命中时退一步看标题是否包含任一知识点的核心词（时段级匹配）。
    两级都过的才算「上面的知识点和下面的视频对得上」。
    """
    title = str(item.get("title") or "")
    keyword = str(item.get("matched_keyword") or "").strip()
    # 关键词形如「考研 不定积分概念与性质」，末段即知识点名
    kp_name = keyword.split(" ", 1)[-1] if " " in keyword else keyword
    strict_tokens = token_map.get(kp_name)
    if strict_tokens and any(token in title for token in strict_tokens):
        return kp_name
    for name, tokens in token_map.items():
        if any(token in title for token in tokens):
            return name
    return ""


def _filter_video_result(result: Dict, token_map: Dict[str, List[str]]) -> None:
    """就地过滤检索结果：只保留与知识点匹配的视频，并标注对应知识点。"""
    kept: List[Dict] = []
    for item in result.get("items", []):
        matched_kp = _video_relevance(item, token_map)
        if matched_kp:
            item["matched_kp"] = matched_kp
            kept.append(item)
    result["items"] = kept
    result["available"] = bool(kept)


def _leaf_points(db: Session, goal_id: int) -> List[KnowledgePoint]:
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)
    ).all()
    if not points:
        return []
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids]
    return leaves or list(points)


def _relevant_points(
    points: List[KnowledgePoint], exam_name: str
) -> List[KnowledgePoint]:
    """只保留与本场考试同学科的知识点。

    一个目标里可能同时挂着多套学科包的知识点（例如 CET-4 目标里混进数学包），
    如果不筛，会给英语考生排出「学线性代数」的课表。这里按学科关键词判定，
    判不出学科的知识点保留（宁可多留也不漏考点）。
    """
    if not points:
        return []
    english_exam = item_policy.exam_is_english(exam_name)
    kept: List[KnowledgePoint] = []
    for point in points:
        name = point.name or ""
        is_science = any(hint in name for hint in item_policy.SCIENCE_KP_HINTS)
        is_english = any(hint in name for hint in item_policy.ENGLISH_KP_HINTS)
        if english_exam:
            # 英语考试：数学/理科类知识点一律排除
            if is_science and not is_english:
                continue
        else:
            # 非英语考试：英语语言类知识点排除（除非考试本身就是英语类，已在上面处理）
            if is_english:
                continue
        kept.append(point)
    return kept or points


def _mastery_map(db: Session, user_id: int, goal_id: int) -> Dict[int, float]:
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in _leaf_points(db, goal_id)] or [0]),
        )
    ).all()
    return {row.kp_id: row.value for row in rows}


def _mistake_map(db: Session, user_id: int, goal_id: int) -> Dict[int, int]:
    rows = db.execute(
        select(Mistake.kp_id, func.count(Mistake.id))
        .where(Mistake.user_id == user_id, Mistake.goal_id == goal_id, Mistake.kp_id.isnot(None))
        .group_by(Mistake.kp_id)
    ).all()
    return {row[0]: row[1] for row in rows if row[0]}


def _phase_windows(goal: Goal, today: date) -> List[Dict]:
    """按剩余天数切阶段，返回每个阶段的起止日期与天数。

    与文档 5.5 的阶段状态机一致：基础期（>45 天）、强化期（15~45 天）、
    冲刺期（4~14 天）、考前 3 日。剩余天数不足时，从基础期起算。
    """
    total = max((goal.exam_date - today).days, 1)
    boundaries = [
        ("foundation", "基础期", "打牢先修，铺开全部考点"),
        ("reinforce", "强化期", "专题突破，错题补救"),
        ("sprint", "冲刺期", "套卷模考，只补关键漏洞"),
        ("final", "考前 3 日", "轻复习，保持手感与作息"),
    ]
    # 每个阶段的计划天数：基础 40%、强化 30%、冲刺 20%、考前 3 天
    fixed = {"final": 3}
    windows: List[Dict] = []
    cursor = today
    remaining = total
    for index, (key, label, desc) in enumerate(boundaries):
        if remaining <= 0:
            break
        if key == "final":
            days = min(fixed["final"], remaining)
        else:
            ratio = {"foundation": 0.4, "reinforce": 0.3, "sprint": 0.3}[key]
            days = max(1, round(total * ratio))
            days = min(days, remaining - fixed.get("final", 0))
            if index == len(boundaries) - 2 and remaining > 0:
                days = max(days, 1)
        days = max(1, min(days, remaining))
        windows.append(
            {
                "phase": key,
                "label": label,
                "description": desc,
                "start_date": cursor,
                "end_date": cursor + timedelta(days=days - 1),
                "day_count": days,
                "ratio": advanced.PHASE_CONFIG[key]["ratio"],
                "target_retention": advanced.PHASE_CONFIG[key]["target_retention"],
                "total_factor": advanced.PHASE_CONFIG[key]["total_factor"],
            }
        )
        cursor += timedelta(days=days)
        remaining -= days
    return windows


def _stage_exam_day(window: Dict, index: int, total_windows: int) -> bool:
    """阶段考试安排在该阶段的最后一天（最后一个阶段则安排在倒数第 3 天）。"""
    if index < total_windows - 1:
        return True
    return False


def _pick_points_for_slot(
    points: List[KnowledgePoint],
    mastery: Dict[int, float],
    mistakes: Dict[int, int],
    role: str,
    used_today: Dict[int, int],
    limit: int,
) -> List[KnowledgePoint]:
    """按时段角色选知识点。

    - new：按课程序列顺序取「今天该学的新课」（candidates 已按天轮转）
    - practice：优先错过多次的（错题补救）
    - review：优先掌握度尚可但需要巩固的

    `used_today` 只记录当天各知识点已被选中的次数：同一天内同一知识点最多出现 2 次，
    保证一天覆盖面；跨天由课程序列轮转保证不重复。
    """

    def score(point: KnowledgePoint) -> Tuple[float, float]:
        value = mastery.get(point.id, 0.0)
        wrong = mistakes.get(point.id, 0)
        penalty = used_today.get(point.id, 0) * 0.6
        if role == "new":
            key = (1 - value) * 2.0 + point.weight * 0.5 - penalty
        elif role == "practice":
            key = wrong * 1.2 + (1 - value) * 1.5 + point.weight * 0.4 - penalty
        else:
            key = value * 1.2 + wrong * 0.6 + point.weight * 0.3 - penalty
        return (round(key, 4), point.weight)

    if role == "new":
        # 学新课：保持课程序列顺序——candidates 本身就是按天轮转的切片，
        # 排在最前的就是「今天该学的新课」，逐日推进、每天不同；
        # 不再按权重重排（那会让每天的新课都落在同几个高权重考点上）。
        ordered = list(points)
    else:
        # 练题 / 复盘：在当日候选集内按掌握度与错题数排序。
        # candidates 已按课程序列轮转过，所以相邻两天的考点不会完全重合，
        # 同时掌握度低的、错得多的仍然优先。
        ordered = sorted(points, key=score, reverse=True)
    chosen: List[KnowledgePoint] = []
    for point in ordered:
        if len(chosen) >= limit:
            break
        if used_today.get(point.id, 0) >= 2:
            continue
        chosen.append(point)
        used_today[point.id] = used_today.get(point.id, 0) + 1

    # 窗口太小时额度会提前用尽（早中晚合计 8 次选取、每点最多 2 次）。
    # 此时回填今天已经安排过的考点，保证每个时段都有内容；
    # 晚上复盘本来就应该回到上午/下午刚学过的点，而不是空档。
    needed = min(limit, len(points))
    if len(chosen) < needed:
        refill = [point for point in ordered if point not in chosen]
        if role == "review":
            refill = sorted(
                refill,
                key=lambda point: (used_today.get(point.id, 0), point.weight),
                reverse=True,
            )
        for point in refill:
            if len(chosen) >= needed:
                break
            chosen.append(point)
            used_today[point.id] = used_today.get(point.id, 0) + 1
    return chosen


def _slot_title(role: str, points: List[KnowledgePoint]) -> str:
    names = "、".join(point.name for point in points[:2])
    if role == "new":
        return f"新学：{names}" if names else "新学：核心概念"
    if role == "practice":
        return f"随堂练：{names}" if names else "随堂练：基础题"
    return f"复盘：{names}" if names else "复盘：错题回看"


def _slot_focus(role: str, points: List[KnowledgePoint]) -> str:
    if role == "new":
        return "先看微课视频建立框架，再由苏格拉底导师做一次概念复述，确认真的懂了。"
    if role == "practice":
        return "做完本时段的随堂测，系统即时判分并把错题归因到四类错因，错的当场进错题本。"
    return "回看今天的错题与闪卡，按记忆稳定度安排明天的复习；这一步决定遗忘曲线上的位置。"


def _slot_minutes(role: str, daily_minutes: int) -> int:
    if role == "new":
        return max(30, round(daily_minutes * 0.4))
    if role == "practice":
        return max(30, round(daily_minutes * 0.35))
    return max(20, round(daily_minutes * 0.25))


def _network_for(db: Session, user: User, goal: Goal, points: List[KnowledgePoint]) -> Dict:
    """取这些知识点在真实知识图谱里的节点与边（先修 / 易混淆）。

    依赖关系来自数据库里的 KnowledgeDependency / KnowledgeEdge，不生成假关系。
    """
    if not points:
        return {"nodes": [], "edges": [], "relations": knowledge_graph.RELATION_LABELS}
    graph = knowledge_graph.get_graph(db, user, goal)
    wanted = {point.id for point in points}
    # 把先修/易混淆的另一端一并纳入，时段里只有两三个考点时也能看出关系。
    for edge in graph["edges"]:
        if edge["from"] in wanted or edge["to"] in wanted:
            wanted.add(edge["from"])
            wanted.add(edge["to"])
    nodes = [node for node in graph["nodes"] if node["id"] in wanted]
    edges = [
        edge
        for edge in graph["edges"]
        if edge["from"] in wanted and edge["to"] in wanted
    ]
    prerequisites = []
    for point in points:
        parents = knowledge_map.prerequisites(db, goal.id, point.id, depth=2)
        if parents:
            prerequisites.append({"kp_id": point.id, "name": point.name, "from_kp_ids": parents})
    return {
        "nodes": nodes,
        "edges": edges,
        "relations": graph["relations"],
        "prerequisites": prerequisites,
    }


async def _attach_videos(
    goal: Goal,
    points: List[KnowledgePoint],
    parent_names: Dict[int, str],
    prefix: str,
    limit: int = 3,
) -> Dict:
    """按知识点检索真实视频课程。搜不到就返回 available=False，不伪造。

    候选词按命中率从高到低：
    1. 「学科前缀 + 知识点」（最准，例如「英语 句子结构」）
    2. 「父模块 + 知识点」（例如「翻译 句子结构」）
    3. 「父模块 + 学科」（例如「语法 英语」）

    检索结果必须通过相关性过滤：视频标题必须命中所属知识点的核心词，
    B 站模糊搜索带回来的泛热门视频（标题与考点无关）一律丢弃；
    过滤后不足时用「学科前缀 + 核心词」的更精确关键词重搜一遍。
    """
    if not points:
        return {"items": [], "available": False, "source": "bilibili", "engine": "none",
                "detail": "该时段没有关联知识点"}
    # 每个知识点用「学科前缀 + 知识点名」精确检索；父模块名作为兜底候选，
    # 只有精确词搜不到时才启用，避免泛词稀释结果。
    keywords: List[str] = []
    for point in points[:3]:
        scoped = f"{prefix} {point.name}".strip()
        if scoped and scoped not in keywords:
            keywords.append(scoped)
    token_map = {point.name: _kp_tokens(point.name) for point in points[:3]}
    result = await video_search.search_videos(keywords, limit=limit)
    _filter_video_result(result, token_map)
    if len(result["items"]) < limit:
        # 相关视频不足：用核心词构造更聚焦的检索词再搜一轮
        # （「考研 不定积分概念与性质」往往 0 命中，「考研 不定积分」命中率高）
        refined: List[str] = []
        for name, tokens in token_map.items():
            for token in tokens[:1]:
                scoped = f"{prefix} {token}".strip()
                if scoped and scoped not in keywords and scoped not in refined:
                    refined.append(scoped)
        if refined:
            extra = await video_search.search_videos(refined, limit=limit)
            _filter_video_result(extra, token_map)
            merged_ids = {item["id"] for item in result["items"]}
            for item in extra.get("items", []):
                if item["id"] not in merged_ids:
                    result["items"].append(item)
                    merged_ids.add(item["id"])
            result["available"] = bool(result["items"])
            result["query"] = keywords + refined
    if not result["items"]:
        fallbacks: List[str] = []
        for point in points[:2]:
            parent = parent_names.get(point.id) if parent_names else None
            if parent:
                scoped = f"{parent} {point.name}".strip()
                if scoped not in fallbacks:
                    fallbacks.append(scoped)
        for parent in list(parent_names.values())[:2] if parent_names else []:
            scoped = f"{parent} {prefix}".strip()
            if scoped and scoped not in fallbacks:
                fallbacks.append(scoped)
        if fallbacks:
            result = await video_search.search_videos(fallbacks, limit=limit)
            _filter_video_result(result, token_map)
            result["query"] = keywords + fallbacks
        else:
            result["query"] = keywords
    else:
        result["query"] = (result.get("query") or keywords)[:4]
    return result


def build_plan(
    db: Session,
    user: User,
    goal: Goal,
    today: Optional[date] = None,
    regenerate: bool = False,
) -> Dict:
    """生成（或读取）整套备考方案。

    返回阶段列表与每天的三段课表。课表内容全部来自真实数据：
    知识点来自数据库、依赖关系来自知识图谱、视频来自 B 站搜索接口。
    """
    today = today or date.today()
    points = _relevant_points(_leaf_points(db, goal.id), goal.exam_name)
    if not points:
        raise ValueError("还没有知识点，请先导入学习资料")

    mastery = _mastery_map(db, user.id, goal.id)
    mistakes = _mistake_map(db, user.id, goal.id)
    windows = _phase_windows(goal, today)

    existing_stage = db.scalar(
        select(ExamPrepStage).where(
            ExamPrepStage.user_id == user.id, ExamPrepStage.goal_id == goal.id
        ).order_by(ExamPrepStage.start_date)
    )
    if existing_stage and not regenerate:
        return read_plan(db, user, goal, today)

    # 重建：先清掉旧方案，避免阶段与日期错位
    db.execute(
        delete(ExamPrepDay).where(
            ExamPrepDay.user_id == user.id, ExamPrepDay.goal_id == goal.id
        )
    )
    db.execute(
        delete(ExamPrepStage).where(
            ExamPrepStage.user_id == user.id, ExamPrepStage.goal_id == goal.id
        )
    )
    db.flush()

    stage_rows: List[ExamPrepStage] = []
    day_rows: List[ExamPrepDay] = []
    day_index = 0
    # 课程序列：按重要度（权重、名称）排一条线。课程表式分配——
    # 第 N 天取序列中第 (N mod 总数) 位开始的那一批考点，
    # 于是每过 len(points) 天完整过一轮，相邻两天的考点不重复，
    # 天然形成间隔复习，而不是天天同几个考点。
    curriculum = sorted(points, key=lambda item: (-item.weight, item.name))
    curriculum_size = max(1, len(curriculum))
    for window_index, window in enumerate(windows):
        stage = ExamPrepStage(
            user_id=user.id,
            goal_id=goal.id,
            phase=window["phase"],
            title=f"{window['label']} · {window['description']}",
            start_date=window["start_date"],
            end_date=window["end_date"],
            day_count=window["day_count"],
            ratio=window["ratio"],
            target_retention=window["target_retention"],
        )
        db.add(stage)
        db.flush()
        stage_rows.append(stage)

        exam_on_last_day = _stage_exam_day(window, window_index, len(windows))
        for offset in range(window["day_count"]):
            day_index += 1
            current = window["start_date"] + timedelta(days=offset)
            slots: List[Dict] = []
            used_today: Dict[int, int] = {}
            # 当天的候选考点：课程序列上按天取模的一段小窗口（约 1/8 考点），
            # 窗口每天前进一步，于是每天的课表都往下推进新内容，
            # 而不是天天围着重叠的大窗口里同一批高权重考点打转。
            # 早中晚最多取 3/3/2 个点，同一考点一天最多 2 次，窗口至少要 4 个点。
            day_window = min(len(curriculum), max(4, (curriculum_size + 7) // 8))
            start = (day_index - 1) * day_window % curriculum_size
            candidates = curriculum[start:] + curriculum[:start]
            candidates = candidates[:day_window]
            for meta in SLOTS:
                role = meta["role"]
                limit = 3 if role == "new" else (3 if role == "practice" else 2)
                chosen = _pick_points_for_slot(
                    candidates, mastery, mistakes, role, used_today, limit
                )
                slot = {
                    "slot": meta["slot"],
                    "label": meta["label"],
                    "range": meta["range"],
                    "icon": meta["icon"],
                    "role": role,
                    "role_label": ROLE_LABELS[role],
                    "title": _slot_title(role, chosen),
                    "focus": _slot_focus(role, chosen),
                    "minutes": _slot_minutes(role, goal.daily_minutes),
                    "kp_ids": [point.id for point in chosen],
                    "kp_names": [point.name for point in chosen],
                    "mastery": {
                        str(point.id): round(mastery.get(point.id, 0.0), 3)
                        for point in chosen
                    },
                    "video": {"items": [], "available": False, "source": "bilibili",
                              "engine": "none", "detail": "视频待检索"},
                    "status": "pending",
                }
                if exam_on_last_day and offset == window["day_count"] - 1 and meta["slot"] == "evening":
                    slot["title"] = STAGE_EXAM_TITLE
                    slot["focus"] = (
                        f"本阶段收官：{window['label']}全部考点一次摸底，"
                        "成绩低于目标保持率就要回炉补这一阶段的错题。"
                    )
                    slot["is_stage_exam"] = True
                slots.append(slot)

            day = ExamPrepDay(
                user_id=user.id,
                goal_id=goal.id,
                stage_id=stage.id,
                day_index=day_index,
                day_date=current,
                phase=window["phase"],
                slots=json.dumps(slots, ensure_ascii=False),
                has_stage_exam=bool(
                    exam_on_last_day and offset == window["day_count"] - 1
                ),
                summary=slots[0]["title"] + " → " + slots[1]["title"] + " → " + slots[2]["title"],
            )
            db.add(day)
            day_rows.append(day)

    db.commit()
    record_event(
        db,
        user.id,
        goal.id,
        "exam_prep_plan",
        None,
        {"days": len(day_rows), "stages": len(stage_rows), "phase": windows[0]["phase"] if windows else ""},
    )
    db.commit()
    return read_plan(db, user, goal, today)


def read_plan(db: Session, user: User, goal: Goal, today: Optional[date] = None) -> Dict:
    """读取已生成的备考方案（不重新生成）。"""
    today = today or date.today()
    stages = db.scalars(
        select(ExamPrepStage)
        .where(ExamPrepStage.user_id == user.id, ExamPrepStage.goal_id == goal.id)
        .order_by(ExamPrepStage.start_date)
    ).all()
    days = db.scalars(
        select(ExamPrepDay)
        .where(ExamPrepDay.user_id == user.id, ExamPrepDay.goal_id == goal.id)
        .order_by(ExamPrepDay.day_index)
    ).all()
    stage_map = {stage.id: stage for stage in stages}
    total_minutes = 0
    for day in days:
        for slot in json.loads(day.slots or "[]"):
            total_minutes += int(slot.get("minutes") or 0)
    return {
        "goal_id": goal.id,
        "exam_name": goal.exam_name,
        "exam_date": goal.exam_date.isoformat(),
        "daily_minutes": goal.daily_minutes,
        "today": today.isoformat(),
        "days_left": max((goal.exam_date - today).days, 0),
        "stages": [
            {
                "id": stage.id,
                "phase": stage.phase,
                "title": stage.title,
                "start_date": stage.start_date.isoformat(),
                "end_date": stage.end_date.isoformat(),
                "day_count": stage.day_count,
                "ratio": stage.ratio,
                "target_retention": stage.target_retention,
                "exam_score": stage.exam_score,
                "exam_total": stage.exam_total,
                "exam_passed": stage.exam_passed,
                "exam_engine": stage.exam_engine,
                "exam_at": stage.exam_at.isoformat() if stage.exam_at else None,
                "status": "done" if stage.exam_passed is not None else "pending",
            }
            for stage in stages
        ],
        "days": [
            {
                "id": day.id,
                "day_index": day.day_index,
                "day_date": day.day_date.isoformat(),
                "phase": day.phase,
                "stage_title": stage_map[day.stage_id].title if day.stage_id in stage_map else "",
                "has_stage_exam": day.has_stage_exam,
                "summary": day.summary,
                "slots": json.loads(day.slots or "[]"),
            }
            for day in days
        ],
        "totals": {
            "days": len(days),
            "stages": len(stages),
            "minutes": total_minutes,
            "slots": len(days) * len(SLOTS),
        },
        "version": "exam-prep-v1",
    }


async def day_detail(
    db: Session, user: User, goal: Goal, day_index: int
) -> Dict:
    """某一天的完整课表：三个时段 + 知识网络 + 真实视频。

    视频在这里才真正联网检索（而不是生成方案时全部拉一遍），
    这样打开任意一天都只请求该天需要的几个关键词。
    """
    day = db.scalar(
        select(ExamPrepDay).where(
            ExamPrepDay.user_id == user.id,
            ExamPrepDay.goal_id == goal.id,
            ExamPrepDay.day_index == day_index,
        )
    )
    if day is None:
        raise ValueError("这一天的方案还没有生成")

    point_map = {
        point.id: point
        for point in db.scalars(
            select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
        ).all()
    }
    parent_names = {
        point.id: point_map[point.parent_id].name
        for point in point_map.values()
        if point.parent_id and point.parent_id in point_map
    }
    prefix = _search_prefix(goal.exam_name)
    slots = json.loads(day.slots or "[]")

    async def _fill_slot(slot: dict) -> None:
        chosen = [point_map[kp_id] for kp_id in slot.get("kp_ids", []) if kp_id in point_map]
        slot["network"] = _network_for(db, user, goal, chosen)
        video = await _attach_videos(goal, chosen, parent_names, prefix, limit=3)
        # query 由 _attach_videos 维护（含精搜后的实际检索词），这里不再覆盖
        slot["video"] = video

    # 各时段的视频检索互相独立，并发执行：冷缓存时整页延迟从
    # 「时段数 × 检索超时」降为「单次检索超时」，避免页面等待过久。
    await asyncio.gather(*(_fill_slot(slot) for slot in slots))

    stage = db.scalar(
        select(ExamPrepStage).where(ExamPrepStage.id == day.stage_id)
    )
    return {
        "day_index": day.day_index,
        "day_date": day.day_date.isoformat(),
        "phase": day.phase,
        "has_stage_exam": day.has_stage_exam,
        "summary": day.summary,
        "stage": {
            "id": stage.id,
            "phase": stage.phase,
            "title": stage.title,
            "ratio": stage.ratio,
            "target_retention": stage.target_retention,
            "exam_score": stage.exam_score,
            "exam_total": stage.exam_total,
            "exam_passed": stage.exam_passed,
        }
        if stage
        else None,
        "slots": slots,
        "version": "exam-prep-v1",
    }


def stage_exam_points(
    db: Session, user: User, goal: Goal, phase: str
) -> List[int]:
    """阶段考试要考哪些知识点：本阶段所有天里出现过的知识点（去重、限 12 个）。"""
    days = db.scalars(
        select(ExamPrepDay).where(
            ExamPrepDay.user_id == user.id,
            ExamPrepDay.goal_id == goal.id,
            ExamPrepDay.phase == phase,
        ).order_by(ExamPrepDay.day_index)
    ).all()
    collected: List[int] = []
    for day in days:
        for slot in json.loads(day.slots or "[]"):
            for kp_id in slot.get("kp_ids", []):
                if kp_id not in collected:
                    collected.append(kp_id)
    return collected[:12]


def record_stage_exam(
    db: Session,
    user: User,
    goal: Goal,
    stage_id: int,
    score: int,
    total: int,
    passed: bool,
    engine: str,
) -> Dict:
    """记录一次阶段考试的真实成绩。"""
    stage = db.get(ExamPrepStage, stage_id)
    if stage is None or stage.user_id != user.id or stage.goal_id != goal.id:
        raise ValueError("阶段不存在")
    stage.exam_score = int(score)
    stage.exam_total = int(total)
    stage.exam_passed = bool(passed)
    stage.exam_engine = engine
    stage.exam_at = datetime.utcnow()
    db.commit()
    record_event(
        db,
        user.id,
        goal.id,
        "stage_exam",
        None,
        {"stage_id": stage_id, "score": score, "total": total, "passed": passed},
    )
    db.commit()
    return {
        "stage_id": stage_id,
        "score": stage.exam_score,
        "total": stage.exam_total,
        "passed": stage.exam_passed,
        "engine": stage.exam_engine,
        "target_retention": stage.target_retention,
    }
