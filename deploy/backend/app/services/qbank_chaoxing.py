"""第三方查题题库适配器（柠檬题库 lemtk / LIKE知识库 datam.site 同款查题接口）。

参考文档:
  - https://github.com/destoryD/chaoxing-api  （LIKE知识库 · datam.site）
  - https://docs.lemtk.xyz/get-started.html    （柠檬题库）

接口形态（按「题干 + 选项」查答案，不支持按知识点枚举题目）:
  - 普通查询  POST/GET ``/api/v1/cx``    Token 可选（免费、限流）
  - 高级查询  POST/GET ``/api/v1/mcx``   Token 必填（题目变形时命中率更高）
  - 余额查询  GET      ``/api/v1/balance?email=&token=``

成功响应::

    {"code": 1000, "msg": "success",
     "data": {"answer": "热水#含水稀醇#热乙醇"}}

题型代码（lemtk 文档）: 0 单选 / 1 多选 / 2 填空 / 3 判断 / 4 简答。
"""

import time
from typing import Dict, List, Optional, Tuple

import httpx

from ..config import settings
from ..models import Goal, KnowledgePoint
from . import question_bank

# 对接域名（文档给出两个 CDN 域名，国内访问慢时可切换备用域名）
DEFAULT_BASE_URL = "https://api.lemtk.xyz"
FALLBACK_BASE_URL = "https://api.vanse.top"

# 平台标签（仅用于元数据展示；查题接口本身不接收平台参数）
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

# 标准题型 → lemtk 题型代码
QUESTION_TYPE_MAP = {
    "single_choice": "0",
    "multiple_choice": "1",
    "fill_blank": "2",
    "true_false": "3",
    "short_answer": "4",
    "essay": "4",
}

# 业务返回码 → 内部状态
CODE_STATUS_MAP = {
    1000: "ok",
    1003: "no_answer",
    1009: "invalid_token",
}


class ChaoxingQBankAdapter:
    """查题题库适配器。

    与旧版「按知识点拉题」的适配器保持同名同签名，便于 quiz.py / goals.py
    既有调用链无缝切换；真实能力以接口文档为准：

      - :meth:`lookup` 按题干 + 选项查询答案（真实联网能力）
      - :meth:`check_balance` 查询剩余调用点数
      - :meth:`search` 为兼容旧调用链保留的占位方法，返回 ``lookup_only`` 状态
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
    ):
        """初始化适配器。

        Args:
            api_url: 旧版参数，兼容映射为 base_url
            api_key: 旧版参数，兼容映射为 token
            platform: 平台标签（仅元数据展示）
            timeout: 请求超时秒数
            base_url: 题库对接域名（如 https://api.lemtk.xyz）
            token: Bearer Token（高级查询必填）
            email: 题库注册邮箱（余额查询必填）
            mode: ``cx`` 普通查询 / ``mcx`` 高级查询
        """
        raw_base = (
            base_url
            if base_url is not None
            else api_url if api_url is not None else settings.QBANK_BASE_URL
        )
        self.base_url = (raw_base or "").strip().rstrip("/")
        self.token = (token or api_key or settings.QBANK_TOKEN or "").strip()
        self.email = (email or settings.QBANK_EMAIL or "").strip()
        self.mode = (mode or settings.QBANK_MODE or "cx").strip().lower()
        if self.mode not in ("cx", "mcx"):
            self.mode = "cx"
        self.platform = platform if platform in SUPPORTED_PLATFORMS else "chaoxing"
        self.timeout = max(
            1.0,
            min(float(timeout if timeout is not None else settings.QBANK_TIMEOUT), 30.0),
        )
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
        """是否已配置可用域名。"""
        return bool(self.base_url)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _lookup_path(self) -> str:
        return "/api/v1/mcx" if self.mode == "mcx" else "/api/v1/cx"

    @staticmethod
    def _map_question_type(question_type: str) -> str:
        return QUESTION_TYPE_MAP.get(question_type, "0")

    @staticmethod
    def _normalize_options(options: any) -> Tuple[List[str], str]:
        """把选项规整为列表与 ``|`` 分隔字符串。"""
        if isinstance(options, list):
            opts = [str(opt).strip() for opt in options if str(opt).strip()]
        elif isinstance(options, str):
            opts = [seg.strip() for seg in options.split("|") if seg.strip()]
        else:
            opts = []
        return opts, "|".join(opts)

    @staticmethod
    def _match_option_indexes(answer_texts: List[str], options: any) -> List[int]:
        """把答案文本映射到选项下标（先精确，后包含）。"""
        if not answer_texts:
            return []
        opts, _ = ChaoxingQBankAdapter._normalize_options(options)
        if not opts:
            return []
        indexes: List[int] = []
        for text in answer_texts:
            idx = next((i for i, opt in enumerate(opts) if opt == text), None)
            if idx is None:
                idx = next(
                    (i for i, opt in enumerate(opts) if text in opt or opt in text),
                    None,
                )
            if idx is not None and idx not in indexes:
                indexes.append(idx)
        return indexes

    # ------------------------------------------------------------------ 查题

    async def lookup(
        self,
        question: str,
        question_type: str = "single_choice",
        options: any = None,
    ) -> Dict:
        """按题干 + 选项查询答案。

        Args:
            question: 题干（必填）
            question_type: 标准题型（single_choice / multiple_choice / ...）
            options: 选项列表或 ``|`` 分隔字符串

        Returns:
            元数据字典：status / latency_ms / detail / answer_texts /
            answer_indexes / mode / platform
        """
        started = time.perf_counter()

        if not self.base_url:
            return {
                "status": "not_configured",
                "latency_ms": None,
                "detail": "题库域名未配置（QBANK_BASE_URL）",
                "mode": self.mode,
                "platform": self.platform,
            }

        question = (question or "").strip()
        if not question:
            return {
                "status": "invalid_input",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "detail": "题干不能为空",
                "mode": self.mode,
                "platform": self.platform,
            }

        if self.mode == "mcx" and not self.token:
            return {
                "status": "token_required",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "detail": "高级查询（mcx）必须配置 QBANK_TOKEN",
                "mode": self.mode,
                "platform": self.platform,
            }

        options_list, options_str = self._normalize_options(options)
        body: Dict[str, str] = {
            "v": "1.0",
            "question": question,
            "type": self._map_question_type(question_type),
        }
        if options_str:
            body["options"] = options_str

        url = f"{self.base_url}{self._lookup_path()}"
        try:
            session = await self._get_session()
            response = await session.post(
                url,
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_lookup(data, options_list, started)
        except httpx.TimeoutException:
            return self._fail("timeout", f"请求超时 (>{self.timeout}s)", started)
        except httpx.HTTPError as exc:
            return self._fail("http_error", f"HTTP 错误: {str(exc)[:100]}", started)
        except (ValueError, KeyError, TypeError) as exc:
            return self._fail("parse_error", f"响应解析失败: {str(exc)[:100]}", started)
        except Exception as exc:  # noqa: BLE001
            return self._fail("error", f"未知错误: {str(exc)[:100]}", started)

    def _parse_lookup(self, data: Dict, options: List[str], started: float) -> Dict:
        elapsed = round((time.perf_counter() - started) * 1000)
        base = {"latency_ms": elapsed, "mode": self.mode, "platform": self.platform}

        if not isinstance(data, dict):
            return {**base, "status": "parse_error", "detail": "响应不是 JSON 对象"}

        code = data.get("code")
        msg = str(data.get("msg") or "")

        if code == 1000:
            answer_raw = (data.get("data") or {}).get("answer") or ""
            answer_texts = [seg.strip() for seg in str(answer_raw).split("#") if seg.strip()]
            indexes = self._match_option_indexes(answer_texts, options)
            return {
                **base,
                "status": "ok",
                "answer_texts": answer_texts,
                "answer_indexes": indexes,
                "detail": f"命中 {len(answer_texts)} 项答案" if answer_texts else "接口返回空答案",
            }

        status = CODE_STATUS_MAP.get(code, "api_error")
        return {**base, "status": status, "detail": f"[{code}] {msg or '查题失败'}"}

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
        """查询剩余调用点数（GET /api/v1/balance）。

        需要配置 ``QBANK_TOKEN`` 与 ``QBANK_EMAIL``。
        """
        started = time.perf_counter()
        base = {"latency_ms": None, "mode": self.mode, "platform": self.platform}

        if not self.base_url:
            return {**base, "status": "not_configured", "detail": "题库域名未配置（QBANK_BASE_URL）"}
        if not self.token or not self.email:
            return {
                **base,
                "status": "not_configured",
                "detail": "余额查询需要配置 QBANK_TOKEN 与 QBANK_EMAIL",
            }

        url = f"{self.base_url}/api/v1/balance"
        params = {"email": self.email, "token": self.token}
        try:
            session = await self._get_session()
            response = await session.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            return self._fail("timeout", f"请求超时 (>{self.timeout}s)", started)
        except httpx.HTTPError as exc:
            return self._fail("http_error", f"HTTP 错误: {str(exc)[:100]}", started)
        except (ValueError, KeyError, TypeError) as exc:
            return self._fail("parse_error", f"响应解析失败: {str(exc)[:100]}", started)
        except Exception as exc:  # noqa: BLE001
            return self._fail("error", f"未知错误: {str(exc)[:100]}", started)

        elapsed = round((time.perf_counter() - started) * 1000)
        if not isinstance(data, dict):
            return {"status": "parse_error", "latency_ms": elapsed, "detail": "响应不是 JSON 对象"}

        code = data.get("code")
        msg = str(data.get("msg") or "")
        if code == 1000:
            payload = data.get("data") or {}
            return {
                "status": "ok",
                "latency_ms": elapsed,
                "balance": payload.get("balance"),
                "banned": bool(payload.get("ban")),
                "email": payload.get("email") or self.email,
                "detail": "余额查询成功",
                "mode": self.mode,
                "platform": self.platform,
            }

        status = CODE_STATUS_MAP.get(code, "api_error")
        return {
            "status": status,
            "latency_ms": elapsed,
            "detail": f"[{code}] {msg or '余额查询失败'}",
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
        """兼容旧调用链：这些查题接口不支持按知识点枚举题目。

        Returns:
            ``([], metadata)``，metadata.status 为 ``lookup_only``，
            出题流程会据此继续降级到通用外部接口 / 模型 / 规则题库。
        """
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


# 全局适配器单例（便于复用连接）
_chaoxing_adapter: Optional[ChaoxingQBankAdapter] = None


async def get_chaoxing_adapter() -> ChaoxingQBankAdapter:
    """获取全局适配器实例。"""
    global _chaoxing_adapter
    if _chaoxing_adapter is None:
        _chaoxing_adapter = ChaoxingQBankAdapter()
    return _chaoxing_adapter


async def search_chaoxing(
    goal: Goal,
    point: KnowledgePoint,
    limit: int = 2,
) -> Tuple[List[Dict], Dict]:
    """兼容旧调用链：按知识点查询（当前查题接口不支持，返回空列表与说明）。"""
    adapter = await get_chaoxing_adapter()
    return await adapter.search(
        knowledge_point=point.name,
        exam_name=goal.exam_name,
        count=max(1, min(int(limit), 10)),
        question_type="single_choice",
    )
