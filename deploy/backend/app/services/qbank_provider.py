"""查题题库适配器工厂：按 ``QBANK_PROVIDER`` 返回对应供应商的适配器。

目前支持：
    - ``lemtk``  柠檬题库 / LIKE知识库同款接口（``qbank_chaoxing``）
    - ``gomooc`` ZERO 网课题库接口（``qbank_gomooc``）

配置 ``QBANK_FALLBACK_PROVIDER`` 后再包一层 :class:`ChainedQBankAdapter`：
主供应商额度用尽 / Token 失效 / 超时 / 暂无答案时自动换下一家，
返回的 metadata 会带上 ``provider`` 说明这次答案到底来自谁。

两个适配器的公共接口一致：``lookup`` / ``check_balance`` / ``search`` / ``close``。
"""

from typing import Dict, List, Optional, Tuple, Union

from ..config import settings
from .qbank_chaoxing import ChaoxingQBankAdapter
from .qbank_gomooc import GomoocQBankAdapter

# 供应商别名 → 标准名
PROVIDER_ALIASES = {
    "lemtk": "lemtk",
    "ningmeng": "lemtk",
    "gomooc": "gomooc",
    "zero": "gomooc",
    "zerobank": "gomooc",
}

SUPPORTED_PROVIDERS = ("lemtk", "gomooc")

QBankAdapter = Union[ChaoxingQBankAdapter, GomoocQBankAdapter]

# 这些状态说明「这家现在给不出答案」，值得换下一家再试
FALLBACK_STATUSES = {
    "not_configured",
    "token_required",
    "invalid_token",
    "quota_exhausted",
    "no_answer",
    "timeout",
    "http_error",
    "parse_error",
    "api_error",
    "error",
}


def resolve_provider() -> str:
    """把配置里的供应商名（含别名）规整为标准名，未知值退回 lemtk。"""
    raw = (settings.QBANK_PROVIDER or "lemtk").strip().lower()
    return PROVIDER_ALIASES.get(raw, "lemtk")


def _build(provider: str, platform: str) -> QBankAdapter:
    if provider == "gomooc":
        return GomoocQBankAdapter(platform=platform)
    return ChaoxingQBankAdapter(platform=platform)


class ChainedQBankAdapter:
    """按顺序尝试多个供应商，主供应商给不出答案时自动降级。"""

    def __init__(self, adapters: List[QBankAdapter], names: List[str]):
        self.adapters = adapters
        self.names = names

    @property
    def configured(self) -> bool:
        return any(adapter.configured for adapter in self.adapters)

    async def close(self) -> None:
        for adapter in self.adapters:
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001
                pass

    async def lookup(
        self,
        question: str,
        question_type: str = "single_choice",
        options: any = None,
    ) -> Dict:
        primary_meta: Optional[Dict] = None
        for index, adapter in enumerate(self.adapters):
            meta = await adapter.lookup(
                question=question, question_type=question_type, options=options
            )
            meta = dict(meta)
            meta["provider"] = self.names[index]
            if index > 0 and primary_meta is not None:
                meta["path"] = " → ".join(self.names[: index + 1])
                meta["primary_status"] = primary_meta.get("status")
                meta["primary_detail"] = primary_meta.get("detail")
            if meta.get("status") == "ok":
                return meta
            if index == 0:
                primary_meta = meta
            if meta.get("status") not in FALLBACK_STATUSES:
                return meta
        return primary_meta or {
            "status": "not_configured",
            "latency_ms": None,
            "detail": "没有可用的题库适配器",
        }

    async def check_balance(self) -> Dict:
        results = []
        for index, adapter in enumerate(self.adapters):
            meta = dict(await adapter.check_balance())
            meta["provider"] = self.names[index]
            results.append(meta)
            if meta.get("status") == "ok":
                meta["path"] = " → ".join(self.names[: index + 1])
                return meta
        if len(results) == 1:
            return results[0]
        return {
            "status": "not_supported",
            "latency_ms": None,
            "detail": "；".join(
                f"{item['provider']}: {item.get('detail') or item.get('status')}"
                for item in results
            ),
            "providers": [item["provider"] for item in results],
        }

    async def search(
        self,
        knowledge_point: str,
        exam_name: str = "",
        count: int = 2,
        question_type: str = "single_choice",
    ) -> Tuple[List[Dict], Dict]:
        # 两家都只支持按题干查答案，这里保持同一套说明
        return await self.adapters[0].search(
            knowledge_point=knowledge_point,
            exam_name=exam_name,
            count=count,
            question_type=question_type,
        )


def create_qbank_adapter(platform: str = "chaoxing") -> Union[QBankAdapter, ChainedQBankAdapter]:
    """按当前配置创建查题适配器；调用方负责 ``await adapter.close()``。"""
    primary = resolve_provider()
    adapters: List[QBankAdapter] = [_build(primary, platform)]
    names: List[str] = [primary]

    fallback_raw = (settings.QBANK_FALLBACK_PROVIDER or "").strip().lower()
    fallback = PROVIDER_ALIASES.get(fallback_raw, "")
    if fallback and fallback != primary:
        adapters.append(_build(fallback, platform))
        names.append(fallback)

    if len(adapters) == 1:
        return adapters[0]
    return ChainedQBankAdapter(adapters, names)
