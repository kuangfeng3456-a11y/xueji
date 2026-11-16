import hashlib
import json
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from .config import settings


class LLMClient:
    """兼容 OpenAI Chat Completions 协议的客户端。

    未配置 LLM_API_KEY / LLM_BASE_URL 时 available 为 False，所有 Agent 自动使用规则兜底，
    保证演示环境与单元测试稳定可复现。
    """

    def __init__(self) -> None:
        primary = (settings.LLM_PRIMARY or "deepseek").lower()
        if primary in ("maas", "pangu") and settings.MAAS_BASE_URL and settings.MAAS_API_KEY:
            self.channel = primary
            self.base_url = settings.MAAS_BASE_URL.rstrip("/")
            self.api_key = settings.MAAS_API_KEY
            self.model = settings.MAAS_MODEL or settings.LLM_MODEL
        else:
            self.channel = "deepseek"
            self.base_url = settings.LLM_BASE_URL.rstrip("/")
            self.api_key = settings.LLM_API_KEY
            self.model = settings.LLM_MODEL
        self.calls = 0
        self.success = 0
        self.failures = 0
        self.total_latency_ms = 0
        self.last_error = ""
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._cache: dict = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_ttl = 600
        self.fallback_base_url = settings.LLM_FALLBACK_BASE_URL.rstrip("/")
        self.fallback_api_key = settings.LLM_FALLBACK_API_KEY
        self.fallback_model = settings.LLM_FALLBACK_MODEL or self.model
        self.fallback_calls = 0

    def _cache_key(self, system: str, user: str, temperature: float, max_tokens: int, model: str = "") -> str:
        normalized = re.sub(r"\s+", " ", (user or "").strip())
        raw = f"{model or self.model}|{system}|{normalized}|{temperature}|{max_tokens}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[str]:
        entry = self._cache.get(key)
        if not entry:
            return None
        expire, value = entry
        if expire < time.time():
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: str) -> None:
        if len(self._cache) > 500:
            now = time.time()
            self._cache = {k: v for k, v in self._cache.items() if v[0] >= now}
            if len(self._cache) > 500:
                self._cache.clear()
        self._cache[key] = (time.time() + self.cache_ttl, value)

    @property
    def available(self) -> bool:
        if not (self.base_url and self.api_key):
            return False
        return time.time() >= self._open_until

    def _record(self, ok: bool, latency_ms: int, error: str = "") -> None:
        self.calls += 1
        self.total_latency_ms += latency_ms
        if ok:
            self.success += 1
            self._consecutive_failures = 0
        else:
            self.failures += 1
            self.last_error = error[:200]
            self._consecutive_failures += 1
            if self._consecutive_failures >= settings.LLM_FAILURE_THRESHOLD:
                self._open_until = time.time() + settings.LLM_COOLDOWN_SECONDS

    def stats(self) -> dict:
        avg = round(self.total_latency_ms / self.calls, 1) if self.calls else 0
        return {
            "channel": self.channel,
            "model": self.model,
            "models": {
                "fast": self._model_for("fast"),
                "general": self._model_for("general"),
                "reasoning": self._model_for("reasoning"),
            },
            "daily_token_budget": settings.LLM_DAILY_TOKEN_BUDGET,
            "audit_enabled": settings.LLM_AUDIT_ENABLED,
            "calls": self.calls,
            "success": self.success,
            "failures": self.failures,
            "avg_latency_ms": avg,
            "circuit_open": time.time() < self._open_until,
            "last_error": self.last_error,
            "primary": settings.LLM_PRIMARY,
            "failure_threshold": settings.LLM_FAILURE_THRESHOLD,
            "cooldown_seconds": settings.LLM_COOLDOWN_SECONDS,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(
                self.cache_hits / max(self.cache_hits + self.cache_misses, 1), 3
            ),
            "cache_size": len(self._cache),
            "cache_ttl": self.cache_ttl,
            "semantic_cache": "exact-normalized",
            "fallback_configured": bool(self.fallback_base_url and self.fallback_api_key),
            "fallback_model": self.fallback_model if self.fallback_base_url else "",
            "fallback_calls": self.fallback_calls,
        }

    def _tier_models(self) -> dict:
        return {
            "fast": settings.LLM_TIER_FAST,
            "general": settings.LLM_TIER_GENERAL,
            "reasoning": settings.LLM_TIER_REASONING,
        }

    def _model_for(self, tier: str = "") -> str:
        """按提示词档位选择模型（文档 6.4）：未配置档位时回落到主模型。"""
        configured = self._tier_models().get((tier or "").lower(), "")
        return (configured or self.model).strip() or self.model

    def _budget_exceeded(self, user_id: Optional[int]) -> bool:
        budget = settings.LLM_DAILY_TOKEN_BUDGET
        if not budget or not user_id:
            return False
        try:
            from .services.llm_audit import daily_tokens

            return daily_tokens(user_id) >= budget
        except Exception:  # noqa: BLE001 - 预算判断失败按可用处理
            return False

    def _audit(self, **kwargs: Any) -> None:
        if not settings.LLM_AUDIT_ENABLED:
            return
        try:
            from .services.llm_audit import record_llm_call

            record_llm_call(**kwargs)
        except Exception:  # noqa: BLE001 - 审计绝不阻断业务
            pass

    def _tokens(self, data: dict, system: str, user: str, content: str) -> tuple:
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict) and (usage.get("prompt_tokens") or usage.get("completion_tokens")):
            return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        try:
            from .services.llm_audit import estimate_tokens

            return estimate_tokens(system + user), estimate_tokens(content)
        except Exception:  # noqa: BLE001
            return 0, 0

    async def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 900,
        *,
        prompt_id: str = "",
        prompt_version: str = "",
        prompt_hash: str = "",
        tier: str = "",
        trace_id: str = "",
        user_id: Optional[int] = None,
        timeout: Optional[float] = None,
        validator_result: str = "",
        repaired: bool = False,
    ) -> Optional[str]:
        audit = {
            "trace_id": trace_id,
            "user_id": user_id,
            "prompt_id": prompt_id,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
            "tier": tier,
            "validator_result": validator_result,
            "repaired": repaired,
        }
        if not self.available:
            if prompt_id:
                self._audit(**audit, model=self.model, success=False, fallback=True, error="llm 未配置或熔断中")
            return None
        if self._budget_exceeded(user_id):
            self.last_error = "daily token budget exceeded"
            self._audit(**audit, model=self._model_for(tier), success=False, fallback=True, error="超出日 token 预算")
            return None
        model = self._model_for(tier)
        cache_key = self._cache_key(system, user, temperature, max_tokens, model)
        cached = self._cache_get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            self._audit(
                **audit,
                model=model,
                route="cache",
                cache_hit=True,
                success=True,
                tokens_in=0,
                tokens_out=0,
            )
            return cached
        self.cache_misses += 1
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        timeout_value = timeout or settings.LLM_TIMEOUT
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_value, connect=min(6.0, timeout_value)),
                trust_env=False,
            ) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                latency = int((time.perf_counter() - started) * 1000)
                self._record(True, latency)
                self._cache_set(cache_key, content)
                tokens_in, tokens_out = self._tokens(data, system, user, content)
                self._audit(
                    **audit,
                    model=model,
                    route="primary",
                    success=True,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency,
                )
                return content
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self._record(False, latency, str(exc))
            if self.fallback_base_url and self.fallback_api_key:
                try:
                    fallback_payload = dict(payload)
                    fallback_payload["model"] = self.fallback_model
                    fallback_headers = {
                        "Authorization": f"Bearer {self.fallback_api_key}",
                        "Content-Type": "application/json",
                    }
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(timeout_value, connect=min(6.0, timeout_value)),
                        trust_env=False,
                    ) as client:
                        resp = await client.post(
                            f"{self.fallback_base_url}/chat/completions",
                            headers=fallback_headers,
                            json=fallback_payload,
                        )
                        resp.raise_for_status()
                        content = resp.json()["choices"][0]["message"]["content"]
                        self.fallback_calls += 1
                        self._cache_set(cache_key, content)
                        self._audit(
                            **audit,
                            model=self.fallback_model,
                            route="fallback",
                            success=True,
                            fallback=True,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                        )
                        return content
                except Exception as fallback_exc:
                    self.last_error = str(fallback_exc)[:200]
                    self._audit(
                        **audit,
                        model=self.fallback_model,
                        route="fallback",
                        success=False,
                        fallback=True,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        error=str(fallback_exc),
                    )
                    return None
            self._audit(
                **audit,
                model=model,
                route="primary",
                success=False,
                latency_ms=latency,
                error=str(exc),
            )
            return None

    @staticmethod
    def _sse_data(line: str) -> Optional[str]:
        """解析一行 SSE：返回 data 载荷，非 data 行返回 None，[DONE] 返回空串标记。"""
        text = line.strip()
        if not text or text.startswith(":"):
            return None
        if not text.startswith("data:"):
            return None
        payload = text[5:].strip()
        if not payload:
            return None
        if payload == "[DONE]":
            return ""
        return payload

    @staticmethod
    def _delta_text(payload: str) -> Tuple[str, Optional[dict]]:
        """从一条 SSE data 中取出增量文本与 usage；解析失败按空增量处理。"""
        try:
            data = json.loads(payload)
        except Exception:  # noqa: BLE001 - 单个分片损坏不应终止整条流
            return "", None
        if not isinstance(data, dict):
            return "", None
        choices = data.get("choices")
        delta = ""
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            chunk = first.get("delta") if isinstance(first.get("delta"), dict) else {}
            raw = chunk.get("content")
            if isinstance(raw, str):
                delta = raw
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        return delta, usage

    async def chat_stream(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 900,
        *,
        prompt_id: str = "",
        prompt_version: str = "",
        prompt_hash: str = "",
        tier: str = "",
        trace_id: str = "",
        user_id: Optional[int] = None,
        timeout: Optional[float] = None,
        validator_result: str = "",
        repaired: bool = False,
    ) -> Optional[AsyncIterator[str]]:
        """流式对话（文档 7.1/7.2「SSE 流式输出」）。

        返回契约：
        - 返回异步生成器时，调用方逐个 await 取到 str 增量；生成器内部已负责审计与熔断计数，
          异常一律被吞掉并安全结束，不会抛出，绝不让 SSE 端点变成 500。
        - 返回 None 表示「不可流式」：未配置 / 熔断中 / 超出日预算 / 缓存未命中之前的前置拒绝，
          调用方应改走规则兜底或非流式路径，而不是把空流当成模型正常输出。
        """
        audit = {
            "trace_id": trace_id,
            "user_id": user_id,
            "prompt_id": prompt_id,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
            "tier": tier,
            "validator_result": validator_result,
            "repaired": repaired,
        }
        # 不可用时不抛错也不伪造内容：交回调用方决定降级文案
        if not self.available:
            if prompt_id:
                self._audit(**audit, model=self.model, success=False, fallback=True, error="llm 未配置或熔断中")
            return None
        if self._budget_exceeded(user_id):
            self.last_error = "daily token budget exceeded"
            self._audit(
                **audit, model=self._model_for(tier), success=False, fallback=True, error="超出日 token 预算"
            )
            return None

        model = self._model_for(tier)
        cache_key = self._cache_key(system, user, temperature, max_tokens, model)
        cached = self._cache_get(cache_key)
        if cached is not None:
            # 命中缓存：一次给完整段，route 标 cache，不谎称模型实时生成
            self.cache_hits += 1
            self._audit(
                **audit,
                model=model,
                route="cache",
                cache_hit=True,
                success=True,
                tokens_in=0,
                tokens_out=0,
            )
            return self._iter_cached(cached)

        self.cache_misses += 1
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            # 多数兼容网关支持在最后一个分片回传 usage，拿不到时下方按长度估算
            "stream_options": {"include_usage": True},
        }
        timeout_value = timeout or settings.LLM_TIMEOUT
        started = time.perf_counter()

        async def _gen() -> AsyncIterator[str]:
            pieces: List[str] = []
            usage: Dict[str, Any] = {}
            finished = False
            try:
                # 连接超时收紧：断网/网关不可达时快速失败走规则兜底，整体读超时仍为 LLM_TIMEOUT
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout_value, connect=min(6.0, timeout_value)),
                    trust_env=False,
                ) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            data_line = self._sse_data(line)
                            if data_line is None:
                                continue
                            if data_line == "":
                                # data: [DONE]，服务端正常收尾
                                break
                            delta, chunk_usage = self._delta_text(data_line)
                            if chunk_usage:
                                usage = chunk_usage
                            if delta:
                                pieces.append(delta)
                                yield delta
                latency = int((time.perf_counter() - started) * 1000)
                content = "".join(pieces)
                self._record(True, latency)
                if content:
                    self._cache_set(cache_key, content)
                tokens_in, tokens_out = self._tokens({"usage": usage}, system, user, content)
                self._audit(
                    **audit,
                    model=model,
                    route="primary",
                    success=True,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency,
                )
                finished = True
            except Exception as exc:  # noqa: BLE001 - 流式异常只终止本条流，不冒泡到端点
                latency = int((time.perf_counter() - started) * 1000)
                self._record(False, latency, str(exc))
                content = "".join(pieces)
                tokens_in, tokens_out = self._tokens({"usage": usage}, system, user, content)
                self._audit(
                    **audit,
                    model=model,
                    route="primary",
                    success=False,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency,
                    error=str(exc),
                )
            finally:
                # 客户端提前断开（关闭页面）也会走到这里：已产出的部分照常计入统计
                if not finished and pieces:
                    self._cache_set(cache_key, "".join(pieces))

        return _gen()

    async def _iter_cached(self, text: str) -> AsyncIterator[str]:
        """缓存回放：保持与流式一致的产出形态。"""
        yield text

    async def chat_json(self, system: str, user: str, **kwargs: Any) -> Optional[Any]:
        text = await self.chat(system, user, **kwargs)
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


llm = LLMClient()