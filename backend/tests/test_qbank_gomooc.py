"""ZERO 网课题库适配器（api.gomooc.net/api.php）单元测试。"""

import asyncio

import pytest

from app.services import qbank_provider
from app.services.qbank_gomooc import GomoocQBankAdapter


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeSession:
    is_closed = False

    def __init__(self, payloads):
        self._payloads = list(payloads) if isinstance(payloads, list) else [payloads]
        self.calls = []

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        index = min(len(self.calls) - 1, len(self._payloads) - 1)
        return _FakeResponse(self._payloads[index])

    async def aclose(self):
        return None


def _run(coro):
    return asyncio.run(coro)


SUCCESS = {
    "code": 200,
    "msg": {
        "title": "查询成功！",
        "tips": "Elasticsearch评分精准 (score: 113.701385)",
        "source": "Elasticsearch",
        "time": "347.1ms",
    },
    "data": [{"question": "题干", "answer": "2", "more": ""}],
}


def test_endpoint_and_params():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession(SUCCESS)

    meta = _run(adapter.lookup(question="f(x)=x² 在 x=1 处的导数为"))

    assert meta["status"] == "ok"
    call = adapter._session.calls[0]
    assert call["url"] == "https://api.gomooc.net/api.php"
    assert call["params"]["token"] == "tok"
    assert call["params"]["question"] == "f(x)=x² 在 x=1 处的导数为"


def test_full_api_url_kept_as_is():
    adapter = GomoocQBankAdapter(api_url="https://api2.gomooc.net/api.php", token="tok")
    assert adapter.base_url == "https://api2.gomooc.net"
    assert adapter.lookup_url == "https://api2.gomooc.net/api.php"


def test_answer_text_and_index_matching():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession(SUCCESS)

    meta = _run(
        adapter.lookup(question="题干", options=["0", "1", "2", "3"])
    )
    assert meta["answer_texts"] == ["2"]
    assert meta["answer_indexes"] == [2]


def test_letter_answer_maps_to_index():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession(
        {"code": 200, "msg": {"title": "ok"}, "data": [{"question": "题干", "answer": "B"}]}
    )

    meta = _run(adapter.lookup(question="题干", options=["甲", "乙", "丙", "丁"]))
    assert meta["answer_indexes"] == [1]


def test_answer_prefix_and_multi_answer_split():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession(
        {
            "code": 200,
            "msg": {"title": "ok"},
            "data": [{"question": "题干", "answer": "正确答案：热水#热乙醇"}],
        }
    )

    meta = _run(
        adapter.lookup(question="题干", options=["热水", "热乙醇", "乙醚"])
    )
    assert meta["answer_texts"] == ["热水", "热乙醇"]
    assert meta["answer_indexes"] == [0, 1]


def test_token_is_required():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="")
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "token_required"


def test_not_configured_without_base_url():
    adapter = GomoocQBankAdapter(base_url="", token="tok")
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "not_configured"


def test_quota_exhausted_code_429():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession(
        {"code": 429, "msg": {"title": "查询次数已用完，请充值", "tips": "剩余次数: 0"}}
    )
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "quota_exhausted"
    assert "剩余次数" in meta["detail"]


def test_empty_token_code_1002():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession({"code": 1002, "msg": {"title": "token为空"}})
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "token_required"


def test_no_answer_retries_with_options_appended():
    adapter = GomoocQBankAdapter(
        base_url="https://api.gomooc.net", token="tok", merge_options=True
    )
    adapter._session = _FakeSession(
        [
            {"code": 1003, "msg": {"title": "暂无答案"}},
            SUCCESS,
        ]
    )

    meta = _run(adapter.lookup(question="题干", options=["0", "1", "2", "3"]))
    assert meta["status"] == "ok"
    assert meta["retried"] is True
    second = adapter._session.calls[1]["params"]["question"]
    assert "A. 0" in second and "D. 3" in second


def test_empty_data_is_no_answer():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    adapter._session = _FakeSession({"code": 200, "msg": {"title": "ok"}, "data": []})
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "no_answer"


def test_check_balance_reports_not_supported():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    meta = _run(adapter.check_balance())
    assert meta["status"] == "not_supported"


def test_search_shim_reports_lookup_only():
    adapter = GomoocQBankAdapter(base_url="https://api.gomooc.net", token="tok")
    questions, meta = _run(adapter.search(knowledge_point="函数与极限"))
    assert questions == []
    assert meta["status"] == "lookup_only"


def test_provider_switches_adapter(monkeypatch):
    monkeypatch.setattr(qbank_provider.settings, "QBANK_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(qbank_provider.settings, "QBANK_PROVIDER", "gomooc")
    assert isinstance(qbank_provider.create_qbank_adapter(), qbank_provider.GomoocQBankAdapter)

    monkeypatch.setattr(qbank_provider.settings, "QBANK_PROVIDER", "zero")
    assert isinstance(qbank_provider.create_qbank_adapter(), qbank_provider.GomoocQBankAdapter)

    monkeypatch.setattr(qbank_provider.settings, "QBANK_PROVIDER", "lemtk")
    assert isinstance(qbank_provider.create_qbank_adapter(), qbank_provider.ChaoxingQBankAdapter)

    monkeypatch.setattr(qbank_provider.settings, "QBANK_PROVIDER", "unknown")
    assert isinstance(qbank_provider.create_qbank_adapter(), qbank_provider.ChaoxingQBankAdapter)


class _StubAdapter:
    """固定返回预设 metadata 的假适配器，用于验证降级链。"""

    configured = True

    def __init__(self, meta):
        self.meta = meta

    async def lookup(self, question, question_type="single_choice", options=None):
        return dict(self.meta)

    async def check_balance(self):
        return dict(self.meta)

    async def search(self, knowledge_point, exam_name="", count=2, question_type="single_choice"):
        return [], {"status": "lookup_only"}

    async def close(self):
        return None


def test_chain_falls_back_when_primary_quota_exhausted():
    chain = qbank_provider.ChainedQBankAdapter(
        [
            _StubAdapter({"status": "quota_exhausted", "detail": "[429] 剩余次数: 0"}),
            _StubAdapter({"status": "ok", "answer_texts": ["2"], "answer_indexes": [2]}),
        ],
        ["gomooc", "lemtk"],
    )
    meta = _run(chain.lookup(question="题干"))

    assert meta["status"] == "ok"
    assert meta["provider"] == "lemtk"
    assert meta["path"] == "gomooc → lemtk"
    assert meta["primary_status"] == "quota_exhausted"


def test_chain_returns_primary_when_all_fail():
    chain = qbank_provider.ChainedQBankAdapter(
        [
            _StubAdapter({"status": "quota_exhausted", "detail": "[429] 剩余次数: 0"}),
            _StubAdapter({"status": "no_answer", "detail": "暂无答案"}),
        ],
        ["gomooc", "lemtk"],
    )
    meta = _run(chain.lookup(question="题干"))

    assert meta["status"] == "quota_exhausted"
    assert meta["provider"] == "gomooc"


def test_chain_skips_fallback_when_primary_hits():
    chain = qbank_provider.ChainedQBankAdapter(
        [
            _StubAdapter({"status": "ok", "answer_texts": ["A"]}),
            _StubAdapter({"status": "ok", "answer_texts": ["B"]}),
        ],
        ["gomooc", "lemtk"],
    )
    meta = _run(chain.lookup(question="题干"))

    assert meta["status"] == "ok"
    assert meta["provider"] == "gomooc"


def test_factory_builds_chain_when_fallback_configured(monkeypatch):
    monkeypatch.setattr(qbank_provider.settings, "QBANK_PROVIDER", "gomooc")
    monkeypatch.setattr(qbank_provider.settings, "QBANK_FALLBACK_PROVIDER", "lemtk")
    adapter = qbank_provider.create_qbank_adapter()

    assert isinstance(adapter, qbank_provider.ChainedQBankAdapter)
    assert adapter.names == ["gomooc", "lemtk"]


def test_factory_ignores_same_provider_fallback(monkeypatch):
    monkeypatch.setattr(qbank_provider.settings, "QBANK_PROVIDER", "lemtk")
    monkeypatch.setattr(qbank_provider.settings, "QBANK_FALLBACK_PROVIDER", "lemtk")
    adapter = qbank_provider.create_qbank_adapter()

    assert isinstance(adapter, qbank_provider.ChaoxingQBankAdapter)
