"""AI 随堂测：DeepSeek 出题 → 判分 → 错因归因 → 更新掌握度 → 动态重排。

B2 干扰项诊断出题：每道选择题的每个错误选项都绑定一种错因（四类错因之一），
学生选错即可直接定位错因，错题自动归类率 100%，不再依赖事后 LLM 二次归因。
错因分配走确定性映射（同一知识点 + 同样的候选干扰项必然得到同样结果），
以满足项目"可复算"的核心原则。
"""

import asyncio
import hashlib
import random
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cache import cache
from ..config import settings
from ..llm import llm
from ..models import Goal, KnowledgePoint, Mastery, Mistake, QuizAttempt, User
from .learning_events import record_event
from .mastery_service import apply_answer
from .planner import replan
from .rules import MISTAKE_CATEGORIES, classify_mistake
from . import item_policy, quiz_material, question_bank, tiku_bank
from .validator import validate_enum

# --------------------------------------------------------------------------
# B2：错因绑定
# --------------------------------------------------------------------------

# 与 rules.MISTAKE_CATEGORIES / agents.diagnoser 完全一致的四类错因
VALID_CAUSES: Tuple[str, ...] = tuple(MISTAKE_CATEGORIES.keys())

# 四类错因对应的典型误解模板；{point}/{option} 由具体知识点与干扰项填充。
CAUSE_MISCONCEPTIONS: Dict[str, str] = {
    "concept": "把「{point}」的概念边界和「{option}」混为一谈",
    "method": "会认概念但用错「{option}」的判定方法与步骤",
    "careless": "概念其实清楚，只是看漏限定条件才误选「{option}」",
    "time": "时间不够仓促作答，没核对就选了「{option}」",
}

# 按知识点名称特征做确定性偏置：命中的错因优先成为该题的主错因。
CAUSE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "concept": ("概念", "定义", "原理", "辨析", "性质", "特点", "含义", "术语"),
    "method": ("方法", "计算", "求解", "证明", "公式", "推导", "步骤", "算法", "编程", "应用"),
    "careless": ("细节", "单位", "符号", "格式", "拼写", "审题", "规范"),
    "time": ("速度", "限时", "流畅", "口语", "听力", "阅读", "速读", "计时"),
}


def _stable_rank(*parts: object) -> int:
    """跨进程稳定的散列值（Python 内置 hash 对 str 加盐，不能用于可复算）。"""
    joined = "|".join(str(part) for part in parts)
    digest = hashlib.md5(joined.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _assign_causes(point_name: str, option_count: int) -> List[str]:
    """为干扰项确定性地分配四类错因。

    先按知识点名称特征把命中的错因置顶，再在未命中的错因之间用知识点散列做轮转，
    因此：命中特征的主错因永远排在第一位，后续干扰项在其余错因间轮换且可复算。
    同一输入必然得到同一输出，四类错因都能被用到。
    """
    if option_count <= 0:
        return []
    primary = [cause for cause in VALID_CAUSES if any(word in point_name for word in CAUSE_KEYWORDS[cause])]
    rest = [cause for cause in VALID_CAUSES if cause not in primary]
    # 轮转只在 rest 内进行，主错因始终占住第一位（无命中时 rest 即全部四类）
    offset = _stable_rank(point_name) % len(rest)
    rotated_rest = rest[offset:] + rest[:offset]
    pool = (primary[:1] + rotated_rest) if primary else rotated_rest
    return [pool[index % len(pool)] for index in range(option_count)]


def _misconception_text(cause: str, point_name: str, option_text: str) -> str:
    template = CAUSE_MISCONCEPTIONS.get(cause) or CAUSE_MISCONCEPTIONS["concept"]
    return template.format(point=point_name, option=option_text)[:100]


def normalize_distractor_cause(raw: object, fallback: str) -> Tuple[str, bool]:
    """把 LLM 给出的 distractor_cause 收敛到四类枚举。

    返回 (合法错因, 是否被规则修复)。支持 "concept：解释文字" 这类带说明的写法；
    非法或缺失值用 validator 的枚举层拦下并回退，绝不放行枚举外的值。
    """
    text = str(raw if raw is not None else "").strip()
    head = text.split("：", 1)[0].split(":", 1)[0].strip().lower() if text else ""
    issues = validate_enum(head or None, VALID_CAUSES, "distractor_cause")
    if not issues and head in VALID_CAUSES:
        return head, False
    return fallback, True


def distractor_binding_issues(causes: List[Optional[str]]) -> List[Dict]:
    """校验一道题的错因绑定：正确项必须为空、干扰项必须落在四类枚举内。"""
    issues: List[Dict] = []
    for index, cause in enumerate(causes):
        if cause is None:
            continue
        issues.extend(validate_enum(cause, VALID_CAUSES, f"distractor_cause[{index}]"))
    return issues


def _goal_points(db: Session, goal_id: int) -> List[KnowledgePoint]:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    parent_ids = {point.parent_id for point in points if point.parent_id}
    leaves = [point for point in points if point.id not in parent_ids]
    return leaves or points


def _bank_offset(goal_id: int, kp_name: str, step: int, language: Optional[str] = None) -> int:
    """同一知识点连续出题时的取题起点：每次后移 step 题，避免反复出同两道。"""
    size = question_bank.bank_of(kp_name, language).get("size") or 0
    if size <= 0:
        return 0
    try:
        count = cache.incr(f"qbank:cursor:{goal_id}:{kp_name}", ttl=QBANK_TTL)
    except Exception:  # noqa: BLE001
        return 0
    return ((count - 1) * max(1, step)) % size


def _module_extras(
    points: List[KnowledgePoint],
    need: int,
    seen: set,
    lang_of: Optional[Dict] = None,
) -> List[dict]:
    """用同一模块下其他知识点的题库补题。

    题库只有 4 道，选 5/6 题时不够；补的题仍属同一学科（如线性代数），
    不会把高数题塞进英语测验，题量够就立即返回。
    """
    extras: List[dict] = []
    for point in points:
        info = question_bank.bank_of(point.name, (lang_of or {}).get(point.id))
        module = info.get("module")
        if not module:
            continue
        for bank in question_bank.banks():
            if bank.get("module") != module or bank["key"] == info.get("key"):
                continue
            for item in question_bank.pick_by_key(bank["key"], 4):
                if item["question"] in seen:
                    continue
                seen.add(item["question"])
                item = dict(item)
                item["kp_name"] = point.name
                item["kp_id"] = point.id
                item["source"] = question_bank.SOURCE_MODULE
                extras.append(item)
                if len(extras) >= need:
                    return extras
    return extras


def _rule_questions(points: List[KnowledgePoint], all_points: List[KnowledgePoint]) -> List[dict]:
    parent_names = [point.name for point in all_points if point.parent_id is None]
    questions = []
    for point in points:
        parent = None
        for candidate in all_points:
            if candidate.id == point.parent_id:
                parent = candidate.name
                break
        correct = parent or "核心模块"
        distractors = [name for name in parent_names if name and name != correct][:3]
        index = 1
        while len(distractors) < 3:
            distractors.append(f"基础模块 {index}")
            index += 1
        options = [correct] + distractors
        random.shuffle(options)
        # 错因绑定与选项顺序无关：先按干扰项文本确定性分配，再映射回打乱后的位置，
        # 因此同一知识点在相同输入下必然得到相同的「选项 → 错因」对应关系。
        cause_map = dict(zip(distractors, _assign_causes(point.name, len(distractors))))
        option_causes: List[Optional[str]] = []
        option_reasons: List[str] = []
        for option in options:
            if option == correct:
                option_causes.append(None)
                option_reasons.append("")
                continue
            cause = cause_map.get(option) or "concept"
            option_causes.append(cause)
            option_reasons.append(_misconception_text(cause, point.name, option))
        questions.append(
            {
                "question": f"「{point.name}」属于下列哪个学习模块？",
                "options": options,
                "answer_index": options.index(correct),
                "explanation": f"「{point.name}」属于「{correct}」，权重 {point.weight}。",
                "kp_name": point.name,
                "kp_id": point.id,
                "option_reasons": option_reasons,
                "distractor_causes": option_causes,
                "source": "规则兜底",
            }
        )
    return questions


def _parse_llm_items(
    raw_items: list,
    points: List[KnowledgePoint],
    exam_name: str,
    limit: int,
    source: str = question_bank.SOURCE_ONLINE,
    material: Optional[Dict] = None,
) -> List[dict]:
    """把模型输出转成题目结构，并按学科策略丢弃中文题干 / 元问题。"""
    point_names = [point.name for point in points]
    name_map = {point.name: point for point in points}
    questions: List[dict] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict) or len(questions) >= limit:
            continue
        options = item.get("options")
        answer_index = item.get("answer_index")
        raw_question = item.get("question")
        if not isinstance(raw_question, str):
            continue
        question = raw_question.strip()
        if not question or not isinstance(options, list) or len(options) != 4:
            continue
        if not isinstance(answer_index, int) or isinstance(answer_index, bool) or not 0 <= answer_index < 4:
            continue
        if not all(isinstance(option, str) and option.strip() for option in options):
            continue
        option_texts = [option.strip()[:120] for option in options]
        if len({option.casefold() for option in option_texts}) != 4:
            continue
        point = name_map.get(str(item.get("kp_name", "")).strip())
        if point is None:
            point = points[len(questions) % len(points)]
        # 学科策略：语言跟着知识点走（数学中文、英语类英文），并拦截元问题
        if item_policy.item_issues(question, option_texts, exam_name, point_names, kp_name=point.name):
            continue
        raw_reasons = item.get("option_reasons")
        # 缺省错因同样来自确定性映射，不依赖随机数
        default_causes = _assign_causes(point.name, len(option_texts))
        # 难度：模型标了 1-4 就用模型的；没标则按题序递增兜底（天然形成递进）
        raw_diff = item.get("difficulty")
        difficulty = (
            raw_diff
            if isinstance(raw_diff, int) and not isinstance(raw_diff, bool) and 1 <= raw_diff <= 4
            else min(4, len(questions) + 1)
        )
        # 解题步骤：模型给几步收几步（每步 ≤200 字，最多 6 步）
        raw_steps = item.get("solution_steps")
        solution_steps = (
            [str(step).strip()[:200] for step in raw_steps if str(step).strip()][:6]
            if isinstance(raw_steps, list)
            else []
        )
        raw_causes = item.get("distractor_causes")
        if not isinstance(raw_causes, list) or len(raw_causes) != 4:
            raw_causes = item.get("distractor_cause")
        option_causes: List[Optional[str]] = []
        for pos, _option_text in enumerate(option_texts):
            if pos == answer_index:
                option_causes.append(None)
                continue
            fallback = default_causes[pos]
            if isinstance(raw_causes, list) and len(raw_causes) == 4:
                cause, _repaired = normalize_distractor_cause(raw_causes[pos], fallback)
            else:
                cause = fallback
            option_causes.append(cause)
        if distractor_binding_issues(option_causes):
            continue
        option_reasons = (
            [str(reason)[:100] for reason in raw_reasons]
            if isinstance(raw_reasons, list) and len(raw_reasons) == 4
            else ["" if pos == answer_index else "概念或方法混淆" for pos in range(4)]
        )
        option_reasons = [
            reason
            or ("" if cause is None else _misconception_text(cause, point.name, option_texts[pos]))
            for pos, (reason, cause) in enumerate(zip(option_reasons, option_causes))
        ]
        questions.append(
            {
                "question": question,
                "options": option_texts,
                "answer_index": answer_index,
                "explanation": str(item.get("explanation", ""))[:600],
                "solution_steps": solution_steps,
                "difficulty": difficulty,
                "kp_name": point.name,
                "kp_id": point.id,
                "option_reasons": option_reasons,
                "distractor_causes": option_causes,
                "source": source,
            }
        )
        if material:
            # 同一次出题的小题共享同一份材料（阅读文章 / 听力音频脚本）
            questions[-1]["material"] = material
    return questions


def _shuffle_options(item: Dict, rng: random.Random) -> Dict:
    """打乱选项顺序，避免正确答案恒为 A。

    模型倾向于把正确答案放在第一个，材料题一组 3-4 题全选 A 就能满分，
    等于没有区分度。选项、错因、误解说明一起同步置换，保证判分口径不变。
    """
    order = list(range(len(item["options"])))
    if len(order) < 2:
        return item
    rng.shuffle(order)
    item["options"] = [item["options"][i] for i in order]
    reasons = item.get("option_reasons") or []
    if len(reasons) == len(order):
        item["option_reasons"] = [reasons[i] for i in order]
    causes = item.get("distractor_causes") or []
    if len(causes) == len(order):
        item["distractor_causes"] = [causes[i] for i in order]
    if isinstance(item.get("answer_index"), int):
        item["answer_index"] = order.index(item["answer_index"])
    return item


async def _llm_material_set(
    points: List[KnowledgePoint],
    all_points: List[KnowledgePoint],
    count: int,
    goal: Optional[Goal],
    kind: str,
) -> List[dict]:
    """生成材料型题组：阅读＝一篇完整文章 + 多题，听力＝一段音频脚本 + 多题。

    真实考试里阅读是一篇文章配多题、听力是一个 section 多段对话，
    所以题量不足时会追加材料（每份材料带自己的 id），而不是硬凑单句题。
    任何环节不合格都返回空，由上层回落普通单选题——宁可降级，也不给假阅读/假听力。
    """
    exam_name = goal.exam_name if goal else ""
    names = [point.name for point in points]
    policy = item_policy.subject_policy(exam_name, names)
    system = quiz_material.system_prompt(kind)
    # 一份材料（180-260 词）+ 多道题轻松超过默认 900 tokens，
    # 按默认值会被截断成半截 JSON，导致材料题永远回落——这里必须放宽
    budget = 3200 if kind == "passage" else 2600

    items: List[dict] = []
    for round_index in range(2):
        need = count - len(items)
        if need <= 0:
            break
        prompt = quiz_material.user_prompt(kind, names, need, policy)
        data = None
        for attempt in range(2):
            ask = prompt
            if attempt == 1:
                ask += "\n上一次输出不完整或不合格，请严格按 JSON 结构重写，正文不要省略。"
            data = await llm.chat_json(system, ask, max_tokens=budget)
            if isinstance(data, dict):
                break
        if not isinstance(data, dict):
            continue
        material = quiz_material.parse_material(data.get("material"), kind)
        raw_items = data.get("questions")
        if not material or not isinstance(raw_items, list):
            continue
        # 材料 id 由「题型 + 标题 + 正文」哈希得出，而不是随机 uuid：
        # 同样的材料必然得到同样的 id，选项打散顺序与判分结果才能复算，
        # 也方便前端按 id 分组（同一份材料的多道题才会显示在一起）。
        seed_text = "|".join(
            [
                kind,
                str(material.get("title") or ""),
                str(material.get("content") or ""),
                str(material.get("audio_script") or ""),
            ]
        )
        material["id"] = hashlib.md5(seed_text.encode("utf-8")).hexdigest()[:8]
        parsed = _parse_llm_items(raw_items, points, exam_name, need, material=material)
        items.extend(parsed)

        # 同一份材料下题量不足：继续基于它出缺的题，避免换材料打断阅读/听力语境
        if parsed and len(items) < count:
            asked = [item["question"] for item in items]
            body = material.get("content") or material.get("audio_script") or ""
            more = (
                "下面是一份已经确定、不允许改写的材料：\n"
                f"{body}\n\n"
                "已经基于它出了这些题：\n- " + "\n- ".join(asked) + "\n"
                f"请再出 {count - len(items)} 道不同的题，必须全部能且只能由上面这段材料回答，"
                "不要换话题、不要引入新材料，不要重复以上题干，只输出 JSON。"
            )
            extra_data = await llm.chat_json(system, more, max_tokens=budget)
            if isinstance(extra_data, dict) and isinstance(extra_data.get("questions"), list):
                extra = _parse_llm_items(
                    extra_data["questions"],
                    points,
                    exam_name,
                    count - len(items),
                    material=material,
                )
                seen_questions = {item["question"].casefold() for item in items}
                for item in extra:
                    if item["question"].casefold() in seen_questions:
                        continue
                    items.append(item)

    # 少于 2 题说明模型根本没围绕材料出题，材料题失去意义
    if len(items) < 2:
        return []
    # 答案位置打散：同一份材料内用材料 id 做种子，结果可复现
    rng = random.Random(str(items[0].get("material", {}).get("id") or "material"))
    for item in items:
        _shuffle_options(item, rng)
    return items[:count]


QBANK_TTL = 7 * 24 * 3600
QBANK_TIMEOUT = 6.0


def _qbank_key(goal_id: int, kp_name: str) -> str:
    return f"qbank:{goal_id}:{kp_name}"


def cached_bank(goal_id: int, kp_name: str, limit: int = 2) -> List[dict]:
    """读取该知识点的在线题库缓存（命中时毫秒级返回）。"""
    try:
        data = cache.get_json(_qbank_key(goal_id, kp_name)) or []
    except Exception:  # noqa: BLE001
        return []
    return data[:limit] if isinstance(data, list) else []


def store_bank(goal_id: int, kp_name: str, items: List[dict]) -> None:
    if not items:
        return
    try:
        cache.set_json(_qbank_key(goal_id, kp_name), items, ttl=QBANK_TTL)
    except Exception:  # noqa: BLE001
        pass


def schedule_online_warm(goal: Goal, point: KnowledgePoint, limit: int = 2) -> None:
    """后台预热在线题库，保证下一次选该知识点时秒回。"""
    if not llm.available:
        return
    if cached_bank(goal.id, point.name, limit):
        return
    goal_id, exam_name, kp_id, kp_name = goal.id, goal.exam_name, point.id, point.name

    async def _warm():
        from types import SimpleNamespace

        pseudo_point = SimpleNamespace(id=kp_id, name=kp_name, goal_id=goal_id)
        pseudo_goal = SimpleNamespace(id=goal_id, exam_name=exam_name)
        try:
            items = await fetch_online_bank(pseudo_goal, pseudo_point, limit)
            store_bank(goal_id, kp_name, items)
        except Exception:  # noqa: BLE001
            pass

    try:
        asyncio.create_task(_warm())
    except RuntimeError:
        # 没有事件循环时直接放弃，不影响主流程
        pass


async def fetch_online_bank(goal: Goal, point: KnowledgePoint, limit: int = 2) -> List[dict]:
    """题源优先级链: 自建题库(tikuAdapter) → 通用外部题库 API → 模型补题。

    1. 自建题库：课程名 = 知识点名，取到的题必然属于该知识点
    2. 通用外部题库 API (QUESTION_BANK_API_URL，按知识点返回题目)
    3. LLM 模型生成
    4. 规则题库 (最后兜底)

    注：lemtk / LIKE知识库 等第三方查题接口只支持按题干查答案
    （见 qbank_chaoxing.lookup / check_balance），不能按知识点枚举题目，
    因此不参与本出题链。
    """
    cached = cached_bank(goal.id, point.name, limit)
    if cached:
        return cached

    # 优先级 1: 自建题库（tikuAdapter）——题库里每个知识点独立成课，取题即对应
    if tiku_bank.configured():
        pool = min(12, max(4, limit * 3))
        items = await tiku_bank.pick(point.name, pool)
        if items:
            store_bank(goal.id, point.name, items)
            return items[:limit]

    # 优先级 2: 通用外部题库 API（按知识点拉题，需要服务端接口地址）
    if settings.QUESTION_BANK_API_URL:
        external_items, _ = await fetch_external_bank(goal, point, limit)
        if external_items:
            store_bank(goal.id, point.name, external_items)
            return external_items[:limit]

    # 优先级 3: LLM 模型生成
    if not llm.available:
        return []
    try:
        items, _ = await asyncio.wait_for(
            _llm_questions([point], [point], limit, goal), timeout=QBANK_TIMEOUT
        )
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return []
    if items:
        store_bank(goal.id, point.name, items)
    return items


async def fetch_external_bank(
    goal: Goal, point: KnowledgePoint, limit: int = 2
) -> Tuple[List[dict], Dict]:
    """真实调用已配置的题库接口并校验响应，不回退其他题源。"""
    if not settings.QUESTION_BANK_API_URL:
        return [], {"status": "not_configured", "latency_ms": None}
    headers = {"Accept": "application/json"}
    if settings.QUESTION_BANK_API_KEY:
        headers["Authorization"] = f"Bearer {settings.QUESTION_BANK_API_KEY}"
    lang = item_policy.language_for_point(goal.exam_name, point.name)
    bank_info = question_bank.bank_of(point.name, lang)
    payload = {
        "exam_name": goal.exam_name,
        "knowledge_point": point.name,
        "module": bank_info.get("module", ""),
        "count": max(1, min(int(limit), 10)),
        "language": bank_info.get("language", lang),
        "question_type": "single_choice",
    }
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=max(1.0, min(settings.QUESTION_BANK_TIMEOUT, 30.0))
        ) as client:
            response = await client.post(
                settings.QUESTION_BANK_API_URL,
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        raw_items = data.get("questions", []) if isinstance(data, dict) else data
        valid_items = _parse_llm_items(
            raw_items if isinstance(raw_items, list) else [],
            [point],
            goal.exam_name,
            limit,
            source=question_bank.SOURCE_EXTERNAL,
        )
        elapsed = round((time.perf_counter() - started) * 1000)
        if not valid_items:
            return [], {
                "status": "invalid_response",
                "latency_ms": elapsed,
                "detail": "接口可访问，但没有返回符合题型与学科校验的题目",
            }
        return valid_items, {
            "status": "ok",
            "latency_ms": elapsed,
            "detail": f"接口连通，返回 {len(valid_items)} 道有效题目",
        }
    except httpx.TimeoutException:
        return [], {
            "status": "timeout",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "detail": "题库接口请求超时",
        }
    except (httpx.HTTPError, ValueError, TypeError):
        return [], {
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "detail": "题库接口请求失败或响应格式无效",
        }


def _balance_by_point(
    items: List[dict], points: List[KnowledgePoint], limit: int
) -> List[dict]:
    """按知识点轮转取题，保证每个知识点先各出一题，再回头补第二题。

    阶段考试要覆盖本阶段全部考点；如果直接按模型返回顺序取，
    12 个考点只出 6 题时会全部落在前 3 个知识点上。
    """
    if limit <= 0:
        return []
    buckets: Dict[int, List[dict]] = defaultdict(list)
    for item in items:
        buckets[item.get("kp_id")].append(item)
    ordered: List[dict] = []
    depth = 0
    while len(ordered) < limit:
        added = False
        for point in points:
            bucket = buckets.get(point.id) or []
            if depth < len(bucket):
                ordered.append(bucket[depth])
                added = True
                if len(ordered) >= limit:
                    break
        if not added:
            break
        depth += 1
    return ordered


async def _llm_questions_per_point(
    points: List[KnowledgePoint],
    all_points: List[KnowledgePoint],
    count: int,
    exam_name: str,
    policy: str,
) -> Tuple[List[dict], str]:
    """多知识点出题：每个知识点单独出一题，再按知识点轮转补齐。

    一次让模型覆盖 12 个知识点出 6 题，模型只会挑 3 个点各出 2 题，
    后面 9 个考点根本没考到——阶段考试必须覆盖全部考点，
    所以这里按知识点逐个调用，再用轮转保证先覆盖后补量。
    """
    per_point = 1
    collected: List[dict] = []
    seen: set = set()
    for point_index, point in enumerate(points):
        if len(collected) >= count:
            break
        single_policy = item_policy.subject_policy(exam_name, [point.name])
        # 逐点出题也要有梯度：按知识点在卷面中的序号轮转难度，整卷呈递进
        difficulty_hint = point_index % 4 + 1
        prompt = (
            f"知识点：{point.name}。生成 {per_point} 道题，难度等级 {difficulty_hint}"
            f"（1 基础概念、2 直接计算、3 综合应用、4 易错变式），"
            f"difficulty 字段必须填 {difficulty_hint}。\n{single_policy}"
        )
        data = await llm.chat_json(
            "你是出题助手，负责生成与真实考试同类的单选题。输出 JSON："
            '{"questions":[{"question":"题干","options":["A","B","C","D"],'
            '"answer_index":0,"difficulty":1,'
            '"explanation":"150-260字详细解析：先给出正确答案的完整推导或计算过程，再逐项说明每个错误选项错在哪里","solution_steps":["第1步","第2步","第3步"],'
            '"kp_name":"知识点名称",'
            '"option_reasons":["","典型误解","典型误解","典型误解"],'
            '"distractor_causes":[null,"concept","method","careless"]}]}。'
            "每题恰好 4 个选项、只有一个正确答案；每个错误项必须是四类错因之一 "
            "concept/method/careless/time；题干必须考学科内容本身，禁止考学习方法、"
            "模块归属或理解方式；题干与选项的语言必须符合 subject_policy；"
            "solution_steps 为 3-6 步解题步骤数组；kp_name 必须是给定的知识点名。只输出 JSON。",
            prompt,
        )
        if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
            continue
        parsed = _parse_llm_items(data["questions"], [point], exam_name, per_point)
        for item in parsed:
            key = (item["question"].lower(), item.get("kp_name", ""))
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)
            if len(collected) >= count:
                break
    if collected:
        return collected[:count], "llm"
    return _rule_questions(points, all_points), "rule"


async def _llm_questions(
    points: List[KnowledgePoint],
    all_points: List[KnowledgePoint],
    count: int,
    goal: Optional[Goal] = None,
    per_point: bool = False,
) -> Tuple[List[dict], str]:
    """出题。

    per_point=True 时按知识点逐个调用模型（阶段考试场景），
    保证每个考点都被考到；默认保持单次调用语义。
    """
    exam_name = goal.exam_name if goal else ""
    point_names = [point.name for point in points]
    if not llm.available:
        return _rule_questions(points, all_points), "rule"
    names = "、".join(point_names)
    policy = item_policy.subject_policy(exam_name, point_names)
    system = (
        "你是出题助手，负责生成与真实考试同类的单选题。题组必须层层递进："
        "按「概念辨析 → 单点计算/方法运用 → 综合应用 → 易错变式/逆向思考」的顺序逐题加深，"
        "严禁把全部题出成同一个难度的送分题。输出 JSON："
        '{"questions":[{"question":"题干","options":["A","B","C","D"],'
        '"answer_index":0,"difficulty":1,'
        '"explanation":"150-260字详细解析：先给出正确答案的完整推导或计算过程，再逐项说明每个错误选项错在哪里、对应什么典型误解；涉及公式必须写出完整公式与代入步骤","solution_steps":["第1步：…","第2步：…","第3步：…"],'
        '"kp_name":"知识点名称",'
        '"option_reasons":["","典型误解","典型误解","典型误解"],'
        '"distractor_causes":[null,"concept","method","careless"]}]}。'
        "每题恰好 4 个选项、只有一个正确答案；每个错误项必须是四类错因之一 concept/method/careless/time；"
        "题干必须考学科内容本身，禁止考学习方法、模块归属或理解方式；"
        "题干与选项的语言必须符合 subject_policy（数学类用中文、英语类用英文）；"
        "difficulty 为 1-4 难度（1 基础概念、2 直接计算、3 综合应用、4 易错变式），必须按题序递增；"
        "solution_steps 为 3-6 步解题步骤数组，每步一句话；kp_name 必须来自给定知识点。只输出 JSON。"
    )
    coverage_hint = (
        "题目必须只考查上面列出的这一个知识点，kp_name 必须是它。"
        if len(points) == 1
        else ""
    )
    prompt = f"知识点：{names}。生成 {count} 道题。{coverage_hint}\n{policy}"
    collected: List[dict] = []
    seen: set = set()
    # 阶段考试要求覆盖全部考点：每个知识点先保底一题，再补齐剩余题量，
    # 否则模型会把所有题都出在前几个知识点上，考不到后面的考点。
    if per_point and len(points) > 1:
        return await _llm_questions_per_point(points, all_points, count, exam_name, policy)
    for attempt in range(2):
        attempt_prompt = prompt
        if attempt == 1:
            attempt_prompt += (
                "\n上一次输出不合格（出现中文题干或学习方法类元问题），"
                "请严格按 subject_policy 重写成真实学科题。"
            )
        data = await llm.chat_json(system, attempt_prompt)
        if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
            continue
        parsed = _parse_llm_items(data["questions"], points, exam_name, count - len(collected))
        # 跨重试去重：同一题只在第一次出现时保留，重试只补新题
        fresh = [item for item in parsed if (item["question"].lower(), item.get("kp_name", "")) not in seen]
        for item in fresh:
            seen.add((item["question"].lower(), item.get("kp_name", "")))
        if len(points) > 1:
            # 多知识点同批出题时按知识点轮转，避免题目全落在第一个考点上
            fresh = _balance_by_point(fresh, points, count - len(collected))
        collected.extend(fresh)
        if len(collected) >= count:
            break
    if collected:
        return collected[:count], "llm"
    return _rule_questions(points, all_points), "rule"


# 难度启发式：外部题库题没有难度字段，按题干特征估计梯度——
# 概念/公式类是基础题，应用/证明/综合类是难题，其余居中。
_EASY_HINTS = ("概念", "定义", "性质", "公式", "结果", "下列", "含义", "等于", "基本")
_HARD_HINTS = ("应用", "综合", "讨论", "证明", "推导", "变式", "最大", "最小", "判断", "比较", "证明")


def _difficulty_rank(item: dict) -> int:
    text = str(item.get("question") or "") + str(item.get("explanation") or "")
    if any(word in text for word in _HARD_HINTS):
        return 2
    if any(word in text for word in _EASY_HINTS):
        return 0
    return 1


def _publish_quiz(
    user: User, goal: Goal, questions: List[dict], engine: str
) -> Dict:
    """落缓存并返回前端可见的题目视图（不泄漏答案）。"""
    quiz_id = uuid.uuid4().hex
    cache.set_json(
        f"quiz:{user.id}:{quiz_id}",
        {"goal_id": goal.id, "questions": questions, "engine": engine},
        ttl=1800,
    )
    public = []
    for index, item in enumerate(questions):
        view = {
            "index": index,
            "question": item["question"],
            "options": item["options"],
            # 难度标签（1-4）：只标梯度、不泄漏答案
            "difficulty": item.get("difficulty"),
            # 与 options 等长；正确项为 null，干扰项为四类错因之一。
            # 不泄漏 answer_index / explanation，判分口径仍由服务端掌握。
            "distractor_causes": item.get("distractor_causes") or [],
            "kp_id": item.get("kp_id"),
            "kp_name": item.get("kp_name"),
            "source": item.get("source") or question_bank.SOURCE_LOCAL,
        }
        material = item.get("material")
        if material:
            # 同一份材料在多题上重复，交给前端按 id 去重渲染
            view["material"] = quiz_material.public_material(material)
        public.append(view)
    return {"quiz_id": quiz_id, "engine": engine, "questions": public}


async def generate_quiz(
    db: Session, user: User, goal: Goal, kp_id: Optional[int], count: int,
    kp_ids: Optional[List[int]] = None,
) -> Dict:
    all_points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    leaves = _goal_points(db, goal.id)
    if not leaves:
        raise ValueError("还没有知识点，请先导入资料")
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user.id,
            Mastery.kp_id.in_([point.id for point in leaves]),
        )
    ).all()
    mastery_map = {row.kp_id: row.value for row in rows}

    is_parent = False
    parent_point: Optional[KnowledgePoint] = None
    if kp_id is not None:
        parent_point = next((point for point in all_points if point.id == kp_id), None)
    if kp_ids:
        # 阶段考试：按指定知识点集合出卷。题目数少于考点数时，
        # 优先考掌握度最低的考点（先补最薄弱的），而不是按顺序取前几个。
        wanted = set(kp_ids)
        selected = [point for point in leaves if point.id in wanted]
        if not selected:
            raise ValueError("所选知识点不存在")
        if count < len(selected):
            selected = sorted(
                selected,
                key=lambda point: (mastery_map.get(point.id, 0.0), -point.weight),
            )[:count]
    elif kp_id is not None:
        children = [point for point in leaves if point.parent_id == kp_id]
        # 父模块自身就是题库知识点时（高等数学 / 线性代数 / 阅读 / 听力），
        # 直接按父模块出题：否则「阅读」的测验会显示成「仔细阅读」「选词填空」，
        # 题目标签与用户所选考点对不上，材料题也拿不到父模块的题型判定。
        if children and parent_point is not None and question_bank.bank_of(parent_point.name):
            selected = [parent_point]
        elif children:
            selected = children[:count]
            is_parent = True
        else:
            selected = [point for point in leaves if point.id == kp_id]
        if not selected:
            raise ValueError("知识点不存在")
    else:
        # 自动选题：只在与本考试同语言的考点里挑。
        # 知识点树里混入他科条目的目标（如英语目标下多挂了数学模块）若不筛，
        # 会按「掌握度最低」优先出到跨学科题，随堂测直接跑题。
        exam_lang = "en" if item_policy.exam_is_english(goal.exam_name) else "zh"
        pool = [
            point
            for point in leaves
            if item_policy.language_for_point(goal.exam_name, point.name) == exam_lang
        ]
        selected = sorted(
            pool or leaves,
            key=lambda point: (mastery_map.get(point.id, 0.0), -point.weight),
        )[:count]
    if not selected:
        raise ValueError("没有可用知识点")

    # 出题顺序：在线题库 / 模型（命中缓存即秒回）→ 内置题库 → 规则题库。
    # 内置题库只作兜底，避免同一批手写题被反复当成真题发放。
    bank_questions: List[dict] = []
    seen: set = set()
    # 指定叶子知识点时把题目都给它；自动选择或指定父模块时按知识点均分，覆盖多个薄弱点
    per_point = (
        1
        if kp_ids
        else count
        if (kp_id is not None and not is_parent)
        else max(1, count // max(1, len(selected)))
    )
    # 每个知识点按学科定语言：中英题库不能互串（「概念辨析」不能拿英语近义词题）
    lang_of = {
        point.id: item_policy.language_for_point(goal.exam_name, point.name)
        for point in selected
    }

    # 阅读 / 听力必须是材料题：一篇完整文章配多题、一段音频脚本配多题。
    # 单句题干 + 四个选项撑不起这两类题型，所以优先走材料题路径；
    # 材料不合格再往下走普通题（内置题库 / 规则题兜底）。
    if not kp_ids and count >= 2 and llm.available:
        kind = quiz_material.material_kind(
            [point.name for point in selected], goal.exam_name
        )
        if kind:
            material_items = await _llm_material_set(
                selected, all_points, count, goal, kind
            )
            if material_items:
                return _publish_quiz(user, goal, material_items, "llm")

    live_enabled = settings.QUIZ_LIVE_FIRST and (
        llm.available or bool(settings.QUESTION_BANK_API_URL) or tiku_bank.configured()
    )
    if live_enabled:
        cold_points = [
            point for point in selected if not cached_bank(goal.id, point.name, per_point)
        ]
        if cold_points:
            # 每个知识点多备 1 题进缓存，后续轮换才不会每次都是同一道
            pool_size = min(4, max(2, per_point + 1))
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(fetch_online_bank(goal, point, pool_size) for point in cold_points)
                    ),
                    timeout=settings.QUIZ_LIVE_TIMEOUT,
                )
            except Exception:  # noqa: BLE001
                # 在线来源超时或不可用：不阻塞，直接走内置题库兜底
                pass
        for point in selected:
            need = min(per_point, count - len(bank_questions))
            if need <= 0:
                break
            pool = cached_bank(goal.id, point.name, 60)
            if not pool:
                continue
            offset = _bank_offset(goal.id, point.name, need, lang_of.get(point.id)) % len(pool)
            pool = pool[offset:] + pool[:offset]
            taken = 0
            for item in pool:
                if len(bank_questions) >= count or taken >= need:
                    break
                if item["question"] in seen:
                    continue
                seen.add(item["question"])
                item = dict(item)
                item["kp_name"] = point.name
                item["kp_id"] = point.id
                bank_questions.append(item)
                taken += 1

    should_fetch_external = bool(settings.QUESTION_BANK_API_URL)
    should_fetch_model = not should_fetch_external and (
        kp_id is not None and not is_parent and llm.available
    )
    if should_fetch_external:
        online_points = [
            point
            for point in selected
            if (
                not question_bank.bank_of(point.name, lang_of.get(point.id))
                or question_bank.bank_of(point.name, lang_of.get(point.id)).get("size", 0)
                < per_point
            )
            if not any(
                item.get("source") == question_bank.SOURCE_EXTERNAL
                for item in cached_bank(goal.id, point.name, 60)
            )
        ]
        if online_points:
            fetched = await asyncio.gather(
                *(fetch_external_bank(goal, point, per_point) for point in online_points)
            )
            for point, (items, _probe) in zip(online_points, fetched):
                if items:
                    store_bank(goal.id, point.name, items)
    elif should_fetch_model:
        online_points = [
            point
            for point in selected
            if not question_bank.bank_of(point.name, lang_of.get(point.id))
            and not cached_bank(goal.id, point.name, per_point)
        ]
        if online_points:
            await asyncio.gather(*(fetch_online_bank(goal, point, per_point) for point in online_points))
    for point in selected:
        need = min(per_point, count - len(bank_questions))
        if need <= 0:
            break
        offset = _bank_offset(goal.id, point.name, need, lang_of.get(point.id))
        cached_items = cached_bank(goal.id, point.name, 60)
        items = question_bank.pick(point.name, need, offset=offset, language=lang_of.get(point.id))
        if len(items) < need and settings.QUESTION_BANK_API_URL:
            items.extend(
                item
                for item in cached_items
                if item.get("source") == question_bank.SOURCE_EXTERNAL
            )
        if len(items) < need:
            items.extend(
                item
                for item in cached_items
                if item.get("source") != question_bank.SOURCE_EXTERNAL
            )
        if not items:
            # 在线来源未命中时后台预热，不阻塞默认出题流程。
            schedule_online_warm(goal, point)
        for item in items:
            if item["question"] in seen:
                continue
            seen.add(item["question"])
            item = dict(item)
            item["kp_name"] = point.name
            item["kp_id"] = point.id
            bank_questions.append(item)
            if len(bank_questions) >= count:
                break

    # 题库题量小于题目数时，用同一模块的其他题库补齐（仍是同科题目，不跨学科）
    if len(bank_questions) < count:
        for item in _module_extras(
            selected, count - len(bank_questions), seen, lang_of
        ):
            bank_questions.append(item)
            if len(bank_questions) >= count:
                break

    # 单知识点测验：题库题按难度启发式排序（基础 → 计算 → 综合应用），
    # 没有难度字段的题按位置补标，保证同一次出题层层递进而非随机难度。
    if kp_id is not None and not is_parent and not kp_ids and len(bank_questions) > 1:
        bank_questions.sort(
            key=lambda item: (_difficulty_rank(item), item.get("question", ""))
        )
    for position, item in enumerate(bank_questions):
        if not item.get("difficulty"):
            item["difficulty"] = min(4, position + 1)

    if bank_questions:
        questions = bank_questions[:count]
        missing = count - len(questions)
        if missing > 0:
            extra, _ = await _llm_questions(
                selected, all_points, missing, goal, per_point=bool(kp_ids)
            )
            existing = {item["question"] for item in questions}
            for item in extra:
                if item["question"] in existing:
                    continue
                existing.add(item["question"])
                questions.append(item)
                if len(questions) >= count:
                    break
        sources = {item.get("source") for item in questions}
        has_tiku = tiku_bank.SOURCE_TIKU in sources
        has_external = question_bank.SOURCE_EXTERNAL in sources
        has_model = question_bank.SOURCE_ONLINE in sources
        has_curated = any(
            source
            not in (question_bank.SOURCE_ONLINE, question_bank.SOURCE_EXTERNAL, tiku_bank.SOURCE_TIKU)
            for source in sources
        )
        if has_tiku:
            # 题目来自自建题库（按知识点建课程），标出来用户才知道不是模型现编的
            engine = (
                "tiku+bank"
                if has_curated
                else "tiku+llm"
                if has_model
                else "tiku+external"
                if has_external
                else "tiku"
            )
        elif has_external:
            engine = (
                "bank+external"
                if has_curated
                else "external+llm"
                if has_model
                else "external"
            )
        else:
            engine = "bank+llm" if has_model and has_curated else "llm" if has_model else "bank"
    elif kp_id is not None:
        # 选了未覆盖的知识点：先秒回规则题，同时后台预热在线题库（下一次直接命中）
        for point in selected:
            schedule_online_warm(goal, point)
        questions, engine = _rule_questions(selected, all_points), "rule"
    else:
        questions, engine = await _llm_questions(
            selected, all_points, count, goal, per_point=bool(kp_ids)
        )
    return _publish_quiz(user, goal, questions, engine)


def grade_quiz(
    db: Session, user: User, goal: Goal, quiz_id: str, answers: List[int]
) -> Dict:
    key = f"quiz:{user.id}:{quiz_id}"
    payload = cache.get_json(key)
    if not payload:
        raise ValueError("题目已过期，请重新生成")
    if payload.get("goal_id") != goal.id:
        raise ValueError("题目不属于当前目标")
    questions = payload.get("questions", [])
    engine = payload.get("engine", "rule")

    correct_count = 0
    wrong = []
    for index, question in enumerate(questions):
        chosen = answers[index] if index < len(answers) else -1
        options = question["options"]
        correct_index = question["answer_index"]
        point = db.get(KnowledgePoint, question["kp_id"]) if question.get("kp_id") else None
        if chosen == correct_index:
            correct_count += 1
            if point:
                apply_answer(db, user.id, point, correct=True)
            continue
        chosen_text = options[chosen] if 0 <= chosen < len(options) else "未作答"
        correct_text = options[correct_index]
        # B2：优先使用选项绑定的错因，做到"做错即诊断"，无需事后二次归因
        causes = question.get("distractor_causes") or []
        bound_cause = causes[chosen] if 0 <= chosen < len(causes) else None
        if isinstance(bound_cause, dict):  # 兼容 {key,text,distractor_cause} 结构
            bound_cause = bound_cause.get("distractor_cause")
        bound_cause, _repaired = normalize_distractor_cause(bound_cause, "")
        if bound_cause:
            category = bound_cause
            label = MISTAKE_CATEGORIES[category]
            _, _, suggestion = classify_mistake(question["question"], chosen_text, correct_text)
            attribution = "option_bound"
        else:
            # 旧题（无错因绑定）仍走规则归因，保证向后兼容
            category, label, suggestion = classify_mistake(
                question["question"], chosen_text, correct_text
            )
            attribution = "rule"
        if point:
            apply_answer(db, user.id, point, correct=False)
            db.add(
                Mistake(
                    user_id=user.id,
                    goal_id=goal.id,
                    kp_id=point.id,
                    question=question["question"],
                    user_answer=chosen_text,
                    correct_answer=correct_text,
                    category=category,
                    category_label=label,
                    suggestion=suggestion,
                    source="quiz",
                    distractor_cause=bound_cause or None,
                )
            )
        reasons = question.get("option_reasons") or []
        misconception = reasons[chosen] if 0 <= chosen < len(reasons) else ""
        wrong.append(
            {
                "index": index,
                "question": question["question"],
                "options": options,
                "chosen": chosen_text,
                "correct": correct_text,
                "explanation": question.get("explanation", ""),
                "solution_steps": question.get("solution_steps") or [],
                "difficulty": question.get("difficulty"),
                "kp_id": point.id if point else question.get("kp_id"),
                "kp_name": question.get("kp_name"),
                "category": category,
                "category_label": label,
                "misconception": misconception,
                "distractor_cause": bound_cause or "",
                "attribution": attribution,
            }
        )
    db.commit()

    changes = []
    if wrong:
        result = replan(db, user.id, goal, trigger="quiz")
        changes = result["changes"]
        from .practice_loop import steer_today

        seen = set()
        for item in wrong:
            kp_id = item.get("kp_id")
            if not kp_id or kp_id in seen:
                continue
            seen.add(kp_id)
            point = db.get(KnowledgePoint, kp_id)
            if point:
                steer_today(db, user, goal, point, f"随堂测答错了「{point.name}」，今天先补这一处。")
    cache.delete(key)

    total = len(questions)
    score = round(correct_count / total * 100) if total else 0
    db.add(
        QuizAttempt(
            quiz_id=quiz_id,
            user_id=user.id,
            goal_id=goal.id,
            score=score,
            correct=correct_count,
            total=total,
            wrong_count=len(wrong),
            engine=engine,
        )
    )
    record_event(
        db,
        user.id,
        goal.id,
        "quiz",
        payload={
            "score": score,
            "correct": correct_count,
            "total": total,
            "wrong_count": len(wrong),
            "engine": engine,
        },
    )
    db.commit()
    # 交卷后才放出材料原文：听力题在此之前只给音频脚本，不给可读文本
    materials = []
    seen_material = set()
    for question in questions:
        material = question.get("material")
        if not material:
            continue
        mid = material.get("id")
        if mid in seen_material:
            continue
        seen_material.add(mid)
        view = dict(material)
        if material.get("kind") == "listening":
            view["transcript"] = material.get("audio_script")
        materials.append(view)

    return {
        "score": score,
        "total": total,
        "correct": correct_count,
        "wrong": wrong,
        "materials": materials,
        "replan_changes": changes,
        "engine": engine,
    }


# --------------------------------------------------------------------------
# 详细解析扩写：外部题库 / 内置题库的题解析往往只有一句话，
# 判分后对解析过短的错题用模型补一份「推导过程 + 逐步步骤」的详细解析。
# 按题干哈希缓存 7 天，同一题不重复扩写；模型不可用时保持原解析不动。
# --------------------------------------------------------------------------

EXPLAIN_MIN_CHARS = 80
EXPLAIN_TTL = 7 * 24 * 3600

_DIFFICULTY_LABELS = {1: "基础概念", 2: "直接计算", 3: "综合应用", 4: "易错变式"}


def difficulty_label(value: object) -> str:
    return _DIFFICULTY_LABELS.get(value if isinstance(value, int) else 0, "")


def _explain_cache_key(question: str) -> str:
    return "quizexplain:" + hashlib.md5(question.encode("utf-8")).hexdigest()


async def enrich_explanations(items: List[dict]) -> None:
    """就地补齐判分结果里的详细解析（只处理解析过短或缺解题步骤的条目）。"""
    if not llm.available or not items:
        return
    targets: List[dict] = []
    for item in items:
        explanation = str(item.get("explanation") or "").strip()
        steps = item.get("solution_steps") or []
        if len(explanation) >= EXPLAIN_MIN_CHARS and len(steps) >= 2:
            continue
        cached = cache.get_json(_explain_cache_key(str(item.get("question") or "")))
        if isinstance(cached, dict) and cached.get("explanation"):
            item["explanation"] = cached["explanation"]
            if cached.get("solution_steps"):
                item["solution_steps"] = cached["solution_steps"]
            continue
        targets.append(item)
    if not targets:
        return

    async def _one(item: dict) -> None:
        chosen = str(item.get("chosen") or "未作答")
        correct = str(item.get("correct") or "")
        prompt = (
            f"题目：{item.get('question')}\n"
            f"学生的错误答案：{chosen}\n"
            f"正确答案：{correct}\n"
            "请站在学科教师的视角给出详细解析，输出 JSON："
            '{"explanation":"200-300字：先完整写出正确答案的推导/计算过程（涉及公式写完整公式与代入步骤），'
            '再专门说明「为什么学生会错成所选答案」，点出该错误背后的典型误解；","solution_steps":["第1步：…","第2步：…","第3步：…"]}。'
            "solution_steps 为 3-6 步，每步一句话。只输出 JSON。"
        )
        try:
            data = await llm.chat_json(
                "你是经验丰富的学科教师，负责把判分结果讲透：既要讲对的过程，也要讲清错的原因。只输出 JSON。",
                prompt,
                max_tokens=900,
            )
        except Exception:  # noqa: BLE001  扩写失败不影响判分返回
            return
        if not isinstance(data, dict):
            return
        explanation = str(data.get("explanation") or "").strip()
        if explanation:
            item["explanation"] = explanation[:800]
        raw_steps = data.get("solution_steps")
        if isinstance(raw_steps, list) and raw_steps:
            item["solution_steps"] = [str(step).strip()[:200] for step in raw_steps if str(step).strip()][:6]
        # 扩写结果落缓存：同一道题以后判分直接命中
        cache.set_json(
            _explain_cache_key(str(item.get("question") or "")),
            {"explanation": item["explanation"], "solution_steps": item.get("solution_steps") or []},
            ttl=EXPLAIN_TTL,
        )

    await asyncio.gather(*(_one(item) for item in targets))

