import asyncio
import json

import pytest

from app import llm as llm_module
from app.llm import LLMClient


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _AsyncClient:
    payload = None
    error = None
    last_url = None
    last_json = None

    def __init__(self, timeout=None, **kwargs):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).last_url = url
        type(self).last_json = json
        if type(self).error:
            raise type(self).error
        return _Response(type(self).payload)


def _client(available=True):
    client = LLMClient()
    client.base_url = "http://llm.local" if available else ""
    client.api_key = "key" if available else ""
    client.model = "pangu"
    return client


def test_llm_unavailable_returns_none():
    client = LLMClient()
    assert client.available is False
    assert asyncio.run(client.chat("s", "u")) is None
    assert asyncio.run(client.chat_json("s", "u")) is None


def test_llm_chat_success(monkeypatch):
    _AsyncClient.payload = {"choices": [{"message": {"content": "今天先做听力。"}}]}
    _AsyncClient.error = None
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _AsyncClient)

    client = _client()
    assert client.available is True
    assert asyncio.run(client.chat("system", "user", temperature=0.3)) == "今天先做听力。"
    assert _AsyncClient.last_url == "http://llm.local/chat/completions"
    assert _AsyncClient.last_json["model"] == "pangu"
    assert _AsyncClient.last_json["messages"][0]["role"] == "system"


def test_llm_chat_error_returns_none(monkeypatch):
    _AsyncClient.error = RuntimeError("network down")
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _AsyncClient)
    assert asyncio.run(_client().chat("s", "u")) is None


def test_llm_chat_json_parses_embedded_object(monkeypatch):
    payload = '前缀说明 {"category":"concept","suggestion":"复习定义"} 结尾'
    _AsyncClient.payload = {"choices": [{"message": {"content": payload}}]}
    _AsyncClient.error = None
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _AsyncClient)

    data = asyncio.run(_client().chat_json("s", "u"))
    assert data == {"category": "concept", "suggestion": "复习定义"}


def test_llm_chat_json_returns_none_without_object(monkeypatch):
    _AsyncClient.payload = {"choices": [{"message": {"content": "没有 JSON"}}]}
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _AsyncClient)
    assert asyncio.run(_client().chat_json("s", "u")) is None


def test_llm_chat_json_returns_none_for_broken_json(monkeypatch):
    _AsyncClient.payload = {"choices": [{"message": {"content": "{broken json}"}}]}
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _AsyncClient)
    assert asyncio.run(_client().chat_json("s", "u")) is None


def test_llm_chat_json_handles_empty_reply(monkeypatch):
    _AsyncClient.payload = {"choices": [{"message": {"content": ""}}]}
    _AsyncClient.error = None
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _AsyncClient)
    assert asyncio.run(_client().chat_json("s", "u")) is None

class _ForbiddenClient:
    """测试环境若创建真实 HTTP 客户端，应立即失败。"""

    def __init__(self, *args, **kwargs):
        raise AssertionError("测试环境不应创建真实 HTTP 客户端发起 LLM 调用")


def test_test_environment_disables_real_llm(monkeypatch):
    from app.config import settings

    assert settings.LLM_BASE_URL == ""
    assert settings.LLM_API_KEY == ""
    assert llm_module.llm.available is False

    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _ForbiddenClient)

    assert asyncio.run(llm_module.llm.chat("system", "user")) is None
    assert asyncio.run(llm_module.llm.chat_json("system", "user")) is None


def test_llm_requires_both_base_url_and_api_key(monkeypatch):
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _ForbiddenClient)

    only_url = LLMClient()
    only_url.base_url = "https://api.deepseek.com/v1"
    only_url.api_key = ""
    assert only_url.available is False
    assert asyncio.run(only_url.chat("s", "u")) is None

    only_key = LLMClient()
    only_key.base_url = ""
    only_key.api_key = "sk-test"
    assert only_key.available is False
    assert asyncio.run(only_key.chat("s", "u")) is None