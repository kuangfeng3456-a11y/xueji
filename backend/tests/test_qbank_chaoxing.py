"""第三方查题题库适配器（lemtk / LIKE知识库 同款接口）单元测试。"""

import asyncio

import httpx
import pytest

from app.services import qbank_chaoxing
from app.services.qbank_chaoxing import ChaoxingQBankAdapter


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeSession:
    is_closed = False

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(self._payload)

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return _FakeResponse(self._payload)

    async def aclose(self):
        return None


def _run(coro):
    return asyncio.run(coro)


def test_type_mapping_follows_lemtk_codes():
    adapter = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz")
    assert adapter._map_question_type("single_choice") == "0"
    assert adapter._map_question_type("multiple_choice") == "1"
    assert adapter._map_question_type("fill_blank") == "2"
    assert adapter._map_question_type("true_false") == "3"
    assert adapter._map_question_type("short_answer") == "4"
    assert adapter._map_question_type("essay") == "4"
    assert adapter._map_question_type("unknown") == "0"


def test_option_normalization_list_and_string():
    opts, joined = ChaoxingQBankAdapter._normalize_options(["热水", "热乙醇", "", "乙醚"])
    assert opts == ["热水", "热乙醇", "乙醚"]
    assert joined == "热水|热乙醇|乙醚"

    opts2, joined2 = ChaoxingQBankAdapter._normalize_options("A|B| B |")
    assert opts2 == ["A", "B", "B"]
    assert joined2 == "A|B|B"


def test_match_option_indexes_exact_then_contains():
    opts = ["0", "1", "2", "3"]
    indexes = ChaoxingQBankAdapter._match_option_indexes(["2"], opts)
    assert indexes == [2]

    indexes = ChaoxingQBankAdapter._match_option_indexes(["热乙醇"], ["热水", "热乙醇", "乙醚"])
    assert indexes == [1]


def test_lookup_success_matches_answer_index():
    adapter = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz", token="tok")
    session = _FakeSession({"code": 1000, "msg": "success", "data": {"answer": "2"}})
    adapter._session = session

    meta = _run(
        adapter.lookup(
            question="f(x)=x² 在 x=1 处的导数为",
            question_type="single_choice",
            options=["0", "1", "2", "3"],
        )
    )

    assert meta["status"] == "ok"
    assert meta["answer_texts"] == ["2"]
    assert meta["answer_indexes"] == [2]
    assert session.calls[0]["url"] == "https://api.lemtk.xyz/api/v1/cx"
    assert session.calls[0]["json"]["type"] == "0"
    assert session.calls[0]["json"]["options"] == "0|1|2|3"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_lookup_mcx_requires_token():
    adapter = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz", mode="mcx", token="")
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "token_required"


def test_lookup_no_answer_and_invalid_token():
    no_answer = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz")
    no_answer._session = _FakeSession({"code": 1003, "msg": "暂无答案"})
    meta = _run(no_answer.lookup(question="题干"))
    assert meta["status"] == "no_answer"

    bad_token = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz", token="bad")
    bad_token._session = _FakeSession({"code": 1009, "msg": "无效的Token"})
    meta2 = _run(bad_token.lookup(question="题干"))
    assert meta2["status"] == "invalid_token"


def test_lookup_not_configured_without_base_url():
    adapter = ChaoxingQBankAdapter(base_url="")
    meta = _run(adapter.lookup(question="题干"))
    assert meta["status"] == "not_configured"


def test_check_balance_success():
    adapter = ChaoxingQBankAdapter(
        base_url="https://api.lemtk.xyz", token="tok", email="user@qq.com"
    )
    adapter._session = _FakeSession(
        {"code": 1000, "msg": "success", "data": {"balance": 8297, "ban": 0, "email": "user@qq.com"}}
    )
    meta = _run(adapter.check_balance())

    assert meta["status"] == "ok"
    assert meta["balance"] == 8297
    assert meta["banned"] is False
    assert meta["email"] == "user@qq.com"
    params = adapter._session.calls[0]["params"]
    assert params["email"] == "user@qq.com"
    assert params["token"] == "tok"


def test_check_balance_missing_config():
    adapter = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz", token="", email="")
    meta = _run(adapter.check_balance())
    assert meta["status"] == "not_configured"


def test_search_shim_reports_lookup_only():
    adapter = ChaoxingQBankAdapter(base_url="https://api.lemtk.xyz")
    questions, meta = _run(adapter.search(knowledge_point="函数与极限"))
    assert questions == []
    assert meta["status"] == "lookup_only"
