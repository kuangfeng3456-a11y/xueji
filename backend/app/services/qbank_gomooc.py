"""ZERO 网课题库（https://api.gomooc.net/api.php）查题适配器。

接口形态（按题干查答案，不支持按知识点枚举题目）::

    GET  /api.php?token=<token>&question=<题干>
    POST /api.php  （表单或查询串传 token、question 均可）

成功响应::

    {"code": 200,
     "msg": {"title": "查询成功！", "tips": "...", "source": "Elasticsearch", "time": "347.1ms"},
     "data": [{"question": "题干", "answer": "正确答案", "more": ""}]}

已知业务码：
    200  查询成功
    1002 token 为空（未配置或参数没带上）
    1009 无效 Token（兼容处理，部分网关返回 401/403）
    429  查询次数已用完（剩余次数: 0，需要充值）
    1003 暂无答案（兼容 404）

与 ``qbank_chaoxing``（柠檬题库 / LIKE知识库）的区别：
    - 只有题干一个业务参数，没有题型、选项、平台参数
    - 一个 token 绑定调用额度，额度耗尽后统一返回 429
    - 不提供余额查询接口
"""

import re
import time
from typing import Dict, List, Optional, Tuple

import httpx

from ..config import settings
from .qbank_chaoxing import ChaoxingQBankAdapter

# 对接域名（api2 为同源备用域名，两者行为一致）
DEFAULT_BASE_URL = "https://api.gomooc.net"
FALLBACK_BASE_URL = "https://api2.gomooc.net"
DEFAULT_ENDPOINT = "/api.php"

# 平台标签（仅用于元数据展示；该接口本身不接收平台参数）
SUPPORTED_PLATFORMS = {
    "chaoxing": "超星学习通",
    "xuexitong": "学习通",
    "zhishuwang": "智慧树",
    "mooc": "中国大学 MOOC",
    "ytx": "学堂在线",
    "zjy": "职教云",
    "zhjy": "智慧职教",
    "yuketang": "雨课堂",
    "kxstar": "考试星",
}

# 业务返回码 → 内部状态
CODE_STATUS_MAP = {
    200: "ok",
    1002: "token_required",
    1003: "no_answer",
    1008: "invalid_token",
    1009: "invalid_token",
    401: "invalid_token",
    403: "invalid_token",
    429: "quota_exhausted",
    404: "no_answer",
}

# 答案文本里的前缀与分隔符
_ANSWER_PREFIX = re.compile(r"^(?:正确答案|参考答案|答案)\s*[：:]\s*")
_ANSWER_SPLIT = re.compile(r"[#\n]+")
# 纯字母形式的答案（A / AB / A,B）
_LETTER_ANSWER = re.compile(r"^[A-Za-zＡ-Ｚ]+$")


class GomoocQBankAdapter:
    """ZERO 网课题库适配器。

    对外接口与 :class:`~app.services.qbank_chaoxing.ChaoxingQBankAdapter`
    保持一致（``lookup`` / ``check_balance`` / ``search`` / ``close``），
    便于通过 ``qbank_provider.create_qbank_adapter()`` 按配置切换。
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        platform: str = "chaoxing",
        timeout: Optional[float] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        email: Optional[str] = None,
        mode: Optional[str] = None,
        endpoint: Optional[str] = None,
        merge_options: Optional[bool] = None,
    ):
        """初始化适配器。

        Args:
            api_url: 完整接口地址（可含 ``/api.php``），优先于 base_url
            api_key: 旧版参数，兼容映射为 token
            platform: 平台标签（仅元数据展示）
            timeout: 请求超时秒数
            base_url: 题库域名（如 https://api.gomooc.net）
            token: 题库 Token（必填，ZERO 无免 token 通道）
            email: 占位参数，该接口没有余额查询，忽略
            mode: 占位参数，该接口没有普通/高级模式，忽略
            endpoint: 接口路径，默认 ``/api.php``
            merge_options: 首轮未命中时，是否把选项拼进题干再查一次
        """
        if api_url is not None:
            raw_url = api_url
        elif base_url is not None:
            raw_url = base_url
        else:
            raw_url = settings.QBANK_GOMOOC_BASE_URL or DEFAULT_BASE_URL
        raw_url = (raw_url or "").strip().rstrip("/")
        if not raw_url:
            self.base_url = ""
            self.lookup_url = ""
        elif raw_url.endswith(".php"):
            self.base_url = raw_url.rsplit("/", 1)[0]
            self.lookup_url = raw_url
        else:
            self.base_url = raw_url
            path = (endpoint or settings.QBANK_GOMOOC_ENDPOINT or DEFAULT_ENDPOINT).strip()
            if not path.startswith("/"):
                path = "/" + path
            self.lookup_url = raw_url + path

        if token is not None:
            raw_token = token
        elif api_key is not None:
            raw_token = api_key
        else:
            raw_token = settings.QBANK_GOMOOC_TOKEN or settings.QBANK_TOKEN
        self.token = (raw_token or "").strip()
        self.platform = platform if platform in SUPPORTED_PLATFORMS else "chaoxing"
        raw_timeout = timeout if timeout is not None else settings.QBANK_TIMEOUT
        self.timeout = max(1.0, min(float(raw_timeout), 30.0))
        self.merge_options = (
            bool(merge_options)
            if merge_options is not None
            else settings.QBANK_GOMOOC_MERGE_OPTIONS
        )
        self.mode = "zero"  # 元数据展示用：该接口没有 cx/mcx 之分
        self._session: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ 基础

    async def _get_session(self) -> httpx.AsyncClient:
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.is_closed:
            await self._session.aclose()

    @property
    def configured(self) -> bool:
        """有域名且有 token 才算可用（该接口没有免 token 通道）。"""
        return bool(self.lookup_url and self.token)

    def _headers(self) -> Dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "xueji-qbank/1.0"}

    # ------------------------------------------------------------ 题干 / 答案

    @staticmethod
    def _normalize_options(options: any) -> Tuple[List[str], str]:
        """复用柠檬题库适配器的选项规整逻辑，保持两套适配器行为一致。"""
        return ChaoxingQBankAdapter._normalize_options(options)

    @staticmethod
    def _compose_question(question: str, options: List[str]) -> str:
        """把选项按 ``A. xx`` 形式拼进题干，提高检索命中率。"""
        if not options:
            return question
        letters = "ABCDEFGHIJ"
        lines = [f"{letters[i]}. {opt}" if i < len(letters) else opt for i, opt in enumerate(options)]
        return question + "\n" + "\n".join(lines)

    @staticmethod
    def _clean_answer(raw: any) -> List[str]:
        """把 ``A#B`` / 换行分隔的答案拆成文本列表，并去掉「答案：」前缀。"""
        if raw is None:
            return []
        text = str(raw).strip()
        if not text:
            return []
        parts = [seg.strip() for seg in _ANSWER_SPLIT.split(text) if seg.strip()]
        cleaned = []
        for seg in parts:
            seg = _ANSWER_PREFIX.sub("", seg).strip()
            if seg and seg not in cleaned:
                cleaned.append(seg)
        return cleaned

    @staticmethod
    def _match_option_indexes(answer_texts: List[str], options: any) -> List[int]:
        """答案文本 → 选项下标：先精确/包含匹配，再按 A/B/C 字母匹配。"""
        if not answer_texts:
            return []
        opts, _ = GomoocQBankAdapter._normalize_options(options)

        indexes = list(ChaoxingQBankAdapter._match_option_indexes(answer_texts, options))

        if not indexes and opts:
            letters = "ABCDEFGHIJ"
            for text in answer_texts:
                if not _LETTER_ANSWER.match(text):
                    continue
                for letter in text.upper():
                    pos = letters.find(letter)
                    if 0 <= pos < len(opts) and pos not in indexes:
                        indexes.append(pos)
        return indexes

    # ------------------------------------------------------------------ 查题

    async def lookup(
        self,
        question: str,
        question_type: str = "single_choice",
        options: any = None,
    ) -> Dict:
        """按题干查询答案；带选项时首轮未命中会自动拼上选项再查一次。"""
        started = time.perf_counter()

        if not self.lookup_url:
            return self._fail("not_configured", "题库地址未配置（QBANK_GOMOOC_BASE_URL）", started)
        if not self.token:
            return self._fail(
                "token_required",
                "ZERO 题库必须配置 token（QBANK_GOMOOC_TOKEN）",
                started,
            )

        question = (question or "").strip()
        if not question:
            return self._fail("invalid_input", "题干不能为空", started)

        options_list, _ = self._normalize_options(options)

        # 第一轮：只发题干，检索最精准
        first = await self._request(question, options_list, started)
        if first.get("status") == "no_answer" and self.merge_options and options_list:
            # 第二轮：题干带上选项再查一次（题库对此类写法命中率更高）
            retry = await self._request(
                self._compose_question(question, options_list), options_list, started
            )
            retry["detail"] = f"拼选项重试：{retry.get('detail') or ''}".strip()
            retry["retried"] = True
            return retry
        return first

    async def _request(self, question: str, options: List[str], started: float) -> Dict:
        params = {"token": self.token, "question": question}
        try:
            session = await self._get_session()
            response = await session.get(
                self.lookup_url,
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_lookup(data, options, started)
        except httpx.TimeoutException:
            return self._fail("timeout", f"请求超时 (>{self.timeout}s)", started)
        except httpx.HTTPError as exc:
            return self._fail("http_error", f"HTTP 错误: {str(exc)[:100]}", started)
        except (ValueError, TypeError) as exc:
            return self._fail("parse_error", f"响应解析失败: {str(exc)[:100]}", started)
        except Exception as exc:  # noqa: BLE001
            return self._fail("error", f"未知错误: {str(exc)[:100]}", started)

    def _parse_lookup(self, data: any, options: List[str], started: float) -> Dict:
        elapsed = round((time.perf_counter() - started) * 1000)
        if not isinstance(data, dict):
            return {
                "status": "parse_error",
                "latency_ms": elapsed,
                "detail": "响应不是 JSON 对象",
                "mode": self.mode,
                "platform": self.platform,
            }

        code = data.get("code")
        msg = data.get("msg")
        if isinstance(msg, dict):
            title = str(msg.get("title") or "")
            tips = str(msg.get("tips") or "")
            source = str(msg.get("source") or "")
            api_time = str(msg.get("time") or "")
        else:
            title, tips, source, api_time = str(msg or ""), "", "", ""

        status = CODE_STATUS_MAP.get(code, "api_error")
        if status != "ok":
            detail = " ".join(part for part in (title, tips) if part) or "查题失败"
            if status == "quota_exhausted":
                detail = detail or "查询次数已用完，请充值后再用"
            return {
                "status": status,
                "latency_ms": elapsed,
                "detail": f"[{code}] {detail}" if code is not None else detail,
                "code": code,
                "mode": self.mode,
                "platform": self.platform,
            }

        items = data.get("data") or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            return {
                "status": "no_answer",
                "latency_ms": elapsed,
                "detail": "接口返回空结果集",
                "mode": self.mode,
                "platform": self.platform,
            }

        best = items[0] if isinstance(items[0], dict) else {}
        answer_texts = self._clean_answer(best.get("answer"))
        if not answer_texts:
            return {
                "status": "no_answer",
                "latency_ms": elapsed,
                "detail": "接口命中题目但答案为空",
                "mode": self.mode,
                "platform": self.platform,
            }

        return {
            "status": "ok",
            "latency_ms": elapsed,
            "detail": f"命中 {len(answer_texts)} 项答案",
            "answer_texts": answer_texts,
            "answer_indexes": self._match_option_indexes(answer_texts, options),
            "matched_question": best.get("question") or "",
            "more": best.get("more") or "",
            "source": source,
            "api_time": api_time,
            "hit_count": len(items),
            "mode": self.mode,
            "platform": self.platform,
        }

    def _fail(self, status: str, detail: str, started: float) -> Dict:
        return {
            "status": status,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "detail": detail,
            "mode": self.mode,
            "platform": self.platform,
        }

    # ------------------------------------------------------------------ 余额

    async def check_balance(self) -> Dict:
        """该题库没有余额接口：如实返回 not_supported，额度耗尽时查题会给 429。"""
        return {
            "status": "not_supported",
            "latency_ms": None,
            "detail": "ZERO 题库未提供余额查询接口；额度用尽时查题返回 code 429（剩余次数: 0）",
            "mode": self.mode,
            "platform": self.platform,
        }

    # ------------------------------------------------------- 兼容旧调用链

    async def search(
        self,
        knowledge_point: str,
        exam_name: str = "",
        count: int = 2,
        question_type: str = "single_choice",
    ) -> Tuple[List[Dict], Dict]:
        """兼容旧调用链：该接口只能按题干查答案，不能按知识点枚举题目。"""
        return [], {
            "status": "lookup_only",
            "latency_ms": None,
            "detail": (
                "该题库为按题干查答案接口，不支持按知识点枚举题目；"
                "请使用 lookup(question, options) 查题"
            ),
            "platform": self.platform,
            "mode": self.mode,
            "knowledge_point": knowledge_point,
        }
