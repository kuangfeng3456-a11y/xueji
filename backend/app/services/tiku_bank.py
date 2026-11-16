"""自建题库（tikuAdapter）客户端：按「知识点 = 课程」取题 / 写题。

为什么要有这一层
----------------
内置题库（question_bank）写在代码里，老师想加题、改答案必须改代码；
而部署好的 tikuAdapter 带 Web 管理后台（增删改查、Word 导入、日志），
更适合当真正的「题库」。所以把题库内容搬到 tikuAdapter，学迹运行时按知识点取题：

    course_name = 知识点名      # 「定积分」的题只会挂到「定积分」名下
    question    = 题干
    options     = JSON 数组字符串
    answer      = JSON 数组字符串（答案文本）

这样「选哪个知识点，就出哪个知识点的题」由数据本身保证，不靠模型猜。

接口要点（tikuAdapter v0.1.0-beta.41）：
  - 鉴权：``Authorization: <jwt>``（裸 token，不带 Bearer 前缀）
  - 取题：``POST /adapter-service/questions/search``（courseName 精确过滤）
  - 写题：``POST /adapter-service/questions``（数组，服务端按 (hash, course_name) 去重）
"""

from __future__ import annotations

import difflib
import json
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx

from ..cache import cache
from ..config import settings

# 题目来源标签（前端展示 / 出题链路判定共用）
SOURCE_TIKU = "题库（tikuAdapter）"
SOURCE_TIKU_SHORT = "tikuAdapter"

# 自建题库题的 plat 标记，便于和第三方来源区分（查询时不过滤）
PLAT_SELF = 99

# JWT 缓存键与有效期（tikuAdapter 的 jwt 未带过期时间，缓存 30 分钟足够）
_TOKEN_KEY = "tiku:jwt"
_TOKEN_TTL = 1800

# 题型：0 单选 / 1 多选 / 2 填空 / 3 判断 / 4 问答
TYPE_SINGLE = 0
TYPE_MULTIPLE = 1
TYPE_BLANK = 2
TYPE_JUDGE = 3


class TikuBankError(RuntimeError):
    """题库调用失败（未配置 / 鉴权失败 / 网络异常）。"""


def configured() -> bool:
    return bool(settings.TIKU_ADAPTER_URL)


class TikuBankClient:
    """轻量客户端：一个实例复用连接，token 走进程内缓存。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url if base_url is not None else settings.TIKU_ADAPTER_URL).rstrip("/")
        self.username = username or settings.TIKU_ADAPTER_USER
        self.password = password if password is not None else settings.TIKU_ADAPTER_PASSWORD
        self.timeout = max(
            1.0, min(float(timeout if timeout is not None else settings.TIKU_ADAPTER_TIMEOUT), 30.0)
        )

    # ---------------------------------------------------------------- 鉴权

    async def _login(self) -> str:
        if not self.base_url:
            raise TikuBankError("题库地址未配置（TIKU_ADAPTER_URL）")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/adapter-service/user/login",
                params={"username": self.username, "password": self.password},
            )
        if response.status_code != 200:
            raise TikuBankError(f"题库登录失败：HTTP {response.status_code}")
        payload = response.json() if response.content else {}
        token = (payload or {}).get("jwt") or ""
        if not token:
            raise TikuBankError("题库登录失败：未返回 jwt")
        return token

    async def token(self, refresh: bool = False) -> str:
        if not refresh:
            try:
                cached = cache.get(_TOKEN_KEY)
            except Exception:  # noqa: BLE001
                cached = None
            if cached:
                return cached
        token = await self._login()
        try:
            cache.set(_TOKEN_KEY, token, ttl=_TOKEN_TTL)
        except Exception:  # noqa: BLE001
            pass
        return token

    async def _request(self, method: str, path: str, *, params=None, json_body=None) -> Dict:
        """带自动重登的请求：401 时刷新 token 重试一次。"""
        if not self.base_url:
            raise TikuBankError("题库地址未配置（TIKU_ADAPTER_URL）")
        url = f"{self.base_url}{path}"
        for attempt in (0, 1):
            token = await self.token(refresh=attempt > 0)
            headers = {"Authorization": token, "Accept": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, url, headers=headers, params=params, json=json_body
                )
            if response.status_code == 401 and attempt == 0:
                continue
            if response.status_code >= 400:
                raise TikuBankError(f"题库请求失败：HTTP {response.status_code}")
            return response.json() if response.content else {}
        raise TikuBankError("题库鉴权失败")

    # ---------------------------------------------------------------- 读

    async def list_by_course(self, course: str, limit: int = 10, page: int = 0) -> List[Dict]:
        """按课程名（= 知识点名）精确取题。"""
        payload = {
            "pageNo": max(0, int(page)),
            "pageSize": max(1, min(int(limit), 100)),
            "courseName": course,
            "plat": -1,
            "type": -1,
        }
        data = await self._request("POST", "/adapter-service/questions/search", json_body=payload)
        items = data.get("items") or [] if isinstance(data, dict) else []
        return [item for item in items if isinstance(item, dict)]

    async def count_by_course(self, course: str) -> int:
        data = await self._request(
            "POST",
            "/adapter-service/questions/search",
            json_body={"pageNo": 0, "pageSize": 1, "courseName": course, "plat": -1, "type": -1},
        )
        total = data.get("total") if isinstance(data, dict) else 0
        return int(total or 0)

    async def courses(self) -> List[str]:
        data = await self._request("GET", "/adapter-service/courses")
        return [str(name) for name in data] if isinstance(data, list) else []

    # ---------------------------------------------------------------- 写

    async def create(self, items: List[Dict]) -> int:
        """批量写题，返回服务端确认新建的条数（重复题会被唯一索引挡掉）。

        tikuAdapter 的实体里 options/answer 是「JSON 字符串」而不是数组
        （见 entity.Tiku：Options string / Answer string），
        且课程字段是下划线风格 course_name —— 直发数组或驼峰会 400 参数错误。
        """
        if not items:
            return 0
        payload = []
        for item in items:
            options = item.get("options") or []
            answer = item.get("answer") or []
            payload.append(
                {
                    "question": str(item.get("question") or "").strip(),
                    "type": int(item.get("type") or 0),
                    # 服务端存储为 JSON 字符串，这里统一序列化
                    "options": json.dumps(options, ensure_ascii=False) if not isinstance(options, str) else options,
                    "answer": json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str) else answer,
                    "plat": int(item.get("plat") or 0),
                    "course_name": str(item.get("course_name") or "").strip(),
                    "extra": str(item.get("extra") or ""),
                }
            )
        payload = [p for p in payload if p["question"] and p["options"] and p["answer"]]
        if not payload:
            return 0
        created = 0
        # 服务端单次请求体不宜过大，按 20 条一批
        for start in range(0, len(payload), 20):
            chunk = payload[start : start + 20]
            data = await self._request("POST", "/adapter-service/questions", json_body=chunk)
            message = str((data or {}).get("message") or "")
            digits = "".join(ch if ch.isdigit() else " " for ch in message).split()
            created += int(digits[-1]) if digits else len(chunk)
        return created

    # ---------------------------------------------------------------- 健康

    async def health(self) -> Dict:
        """探活：能登录 + 能读课程列表即视为可用。"""
        started = time.perf_counter()
        if not self.base_url:
            return {"status": "not_configured", "detail": "TIKU_ADAPTER_URL 未配置"}
        try:
            courses = await self.courses()
        except TikuBankError as exc:
            return {"status": "error", "detail": str(exc), "latency_ms": round((time.perf_counter() - started) * 1000)}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"[:160]}
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "courses": len(courses),
            "base_url": self.base_url,
        }


_client: Optional[TikuBankClient] = None


def get_client() -> TikuBankClient:
    global _client
    if _client is None:
        _client = TikuBankClient()
    return _client


# --------------------------------------------------------------------------
# 记录 → 题目结构
# --------------------------------------------------------------------------


def _loads_array(raw) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def _answer_indexes(answer_texts: List[str], options: List[str]) -> List[int]:
    """答案文本 → 选项下标（先精确，再包含），用于判分。"""
    indexes: List[int] = []
    for text in answer_texts:
        idx = next((i for i, opt in enumerate(options) if opt == text), None)
        if idx is None:
            idx = next((i for i, opt in enumerate(options) if text and (text in opt or opt in text)), None)
        if idx is not None and idx not in indexes:
            indexes.append(idx)
    return indexes


def to_item(raw: Dict, point_name: str = "") -> Optional[Dict]:
    """把 tikuAdapter 的一条记录转成学迹的题目结构；不合格返回 None。

    不合格的典型情况：选项不足 4 个、答案是文本对不上任何选项（无法判分）。
    """
    question = str(raw.get("question") or "").strip()
    options = [opt.strip() for opt in _loads_array(raw.get("options")) if opt.strip()]
    answers = [ans.strip() for ans in _loads_array(raw.get("answer")) if ans.strip()]
    if not question or len(options) < 2 or not answers:
        return None
    indexes = _answer_indexes(answers, options)
    if not indexes:
        return None
    answer_index = indexes[0]
    explanation = str(raw.get("extra") or "").strip()
    return {
        "question": question,
        "options": options,
        "answer_index": answer_index,
        "answer_indexes": indexes,
        "explanation": explanation or f"正确答案：{options[answer_index]}",
        "option_reasons": ["" if i in indexes else "常见错误" for i in range(len(options))],
        "distractor_causes": [None if i in indexes else "concept" for i in range(len(options))],
        "source": SOURCE_TIKU,
        "tiku_id": raw.get("id"),
        "course_name": str(raw.get("course_name") or point_name),
        "kp_name": point_name or str(raw.get("course_name") or ""),
    }


async def pick(point_name: str, limit: int = 2, offset: int = 0) -> List[Dict]:
    """取某知识点的题（先按知识点名精确匹配课程，未命中再做模糊解析）。

    轮换策略：先读该课程第 0 页的一批，再按 offset 旋转，避免每次都是同一题。
    """
    if not configured() or not point_name:
        return []
    limit = max(1, min(int(limit), 20))
    page_size = max(limit, min(20, limit * 4))
    try:
        client = get_client()
        course = await resolve_course(point_name)
        if not course:
            return []
        raws = await client.list_by_course(course, page_size, page=0)
    except (TikuBankError, httpx.HTTPError):
        return []
    except Exception:  # noqa: BLE001
        return []
    items = [item for item in (to_item(raw, point_name) for raw in raws) if item]
    if not items:
        return []
    start = int(offset) % len(items)
    ordered = items[start:] + items[:start]
    return ordered[:limit]


# ---------------------------------------------------------------------------
# 课程名模糊解析：知识点名（来自资料抽取）不必与课程名逐字相同。
# 例如知识点「两个重要极限」可对应课程「函数与极限」，「函数极限」对应「极限」。
# 解析结果缓存 30 分钟，避免每次出题都拉全量课程列表。
# ---------------------------------------------------------------------------
_COURSE_LIST_TTL = 1800
_course_list_cache: Tuple[float, List[str]] = (0.0, [])
_resolve_cache: Dict[str, Optional[str]] = {}
_RESOLVE_MIN_RATIO = 0.62


def _norm_name(name: str) -> str:
    """归一化：去空格/书名号/“第X版”等装饰词，全角转半角，转小写。"""
    text = (name or "").strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"第\s*[一二三四五六七八九十\d]+\s*版", "", text)
    text = re.sub(r"[\s《》·、，,。.\-—_()（）]", "", text)
    return text


async def _course_names() -> List[str]:
    """题库全部课程名（带 TTL 缓存）。"""
    global _course_list_cache
    now = time.time()
    cached_at, names = _course_list_cache
    if names and now - cached_at < _COURSE_LIST_TTL:
        return names
    try:
        names = await get_client().courses()
    except Exception:  # noqa: BLE001  题库不可用时按空处理，出题链自然降级
        names = []
    _course_list_cache = (now, names or [])
    return _course_list_cache[1]


async def resolve_course(point_name: str) -> Optional[str]:
    """把知识点名解析成题库课程名：精确命中 → 包含关系 → 相似度最优。"""
    if not point_name:
        return None
    if point_name in _resolve_cache:
        return _resolve_cache[point_name]

    names = await _course_names()
    if not names:
        # 课程列表暂时拿不到时，仍按知识点名精确取题，且不写入缓存，
        # 以便列表恢复后能再做模糊解析。
        return point_name

    target = _norm_name(point_name)
    result: Optional[str] = None
    # 1) 精确（归一化后全等）
    if target:
        for name in names:
            if _norm_name(name) == target:
                result = name
                break
    # 2) 包含：知识点名包含课程名（或反之），取更长（更具体）的课程名
    if result is None and len(target) >= 2:
        best_len = 0
        for name in names:
            norm = _norm_name(name)
            if len(norm) >= 2 and (norm in target or target in norm) and len(norm) > best_len:
                result, best_len = name, len(norm)
    # 3) 相似度兜底
    if result is None:
        best_ratio, best_name = 0.0, None
        for name in names:
            ratio = difflib.SequenceMatcher(None, target, _norm_name(name)).ratio()
            if ratio > best_ratio:
                best_ratio, best_name = ratio, name
        if best_ratio >= _RESOLVE_MIN_RATIO:
            result = best_name
    _resolve_cache[point_name] = result
    return result


async def coverage(point_names: List[str]) -> Dict:
    """统计题库对给定知识点的覆盖：每个知识点有多少题（含模糊解析）。"""
    result: Dict[str, Dict] = {}
    if not configured():
        return {"status": "not_configured", "points": result}
    for name in point_names:
        if not name:
            continue
        try:
            course = await resolve_course(name)
            total = await get_client().count_by_course(course) if course else 0
        except Exception:  # noqa: BLE001
            total = 0
        result[name] = {"count": total, "covered": total > 0}
    covered = sum(1 for info in result.values() if info["covered"])
    return {
        "status": "ok",
        "points": result,
        "total": len(result),
        "covered": covered,
        "rate": round(covered / len(result), 3) if result else 0.0,
    }
