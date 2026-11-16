"""提示词中心与调用审计接口测试（可信度中心数据源）。"""

from datetime import datetime

from sqlalchemy import func, select

from app.models import LlmCall, PromptVersion


def test_prompts_endpoint_requires_auth(api):
    assert api("GET", "/api/prompts").status_code == 401


def test_prompts_endpoint_lists_all_prompts(api, auth):
    response = api("GET", "/api/prompts", token=auth["token"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 19
    assert body["version"] == "2.0.0"
    assert body["envelope_fields"] == ["data", "evidence_refs", "confidence", "warnings"]
    ids = [item["id"] for item in body["items"]]
    assert ids == [f"P{i:02d}" for i in range(19)]
    p12 = next(item for item in body["items"] if item["id"] == "P12")
    assert p12["tier"] == "general"
    assert len(p12["hash"]) == 64


def test_prompt_detail_returns_contract_and_placeholders(api, auth):
    response = api("GET", "/api/prompts/P12", token=auth["token"])

    assert response.status_code == 200
    body = response.json()
    assert body["name"].startswith("决策解释官")
    assert "decision-explainer" in body["agents"]
    assert "module_data_json" in body["placeholders"]
    assert "<output_contract>" not in body["output_contract"]  # 契约正文本身不含包裹标签
    assert "insights" in body["output_contract"]


def test_prompt_detail_unknown_id_returns_404(api, auth):
    assert api("GET", "/api/prompts/P99", token=auth["token"]).status_code == 404


def test_prompt_sync_is_idempotent(api, auth, db):
    first = api("POST", "/api/prompts/sync", token=auth["token"])
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 19

    second = api("POST", "/api/prompts/sync", token=auth["token"])
    body = second.json()
    assert body["created"] == 0
    assert body["unchanged"] == 19

    total = db.scalar(select(func.count(PromptVersion.id)))
    assert total == 19
    assert db.scalar(
        select(PromptVersion).where(PromptVersion.prompt_id == "P00")
    ).status == "active"


def test_prompt_versions_endpoint_filters_by_id(api, auth):
    api("POST", "/api/prompts/sync", token=auth["token"])

    all_rows = api("GET", "/api/prompts/versions", token=auth["token"]).json()
    assert all_rows["total"] == 19

    filtered = api(
        "GET", "/api/prompts/versions", token=auth["token"], params={"prompt_id": "p03"}
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["prompt_id"] == "P03"


def test_llm_calls_endpoint_aggregates_user_calls(api, auth, db):
    user_id = auth["user"]["id"]
    db.add_all(
        [
            LlmCall(
                user_id=user_id,
                prompt_id="P12",
                prompt_version="2.0.0",
                model="deepseek-chat",
                route="primary",
                tier="general",
                success=True,
                tokens_in=100,
                tokens_out=40,
                latency_ms=120,
                created_at=datetime.utcnow(),
            ),
            LlmCall(
                user_id=user_id,
                prompt_id="P03",
                model="deepseek-chat",
                route="primary",
                success=False,
                fallback=True,
                latency_ms=80,
                error="timeout",
                created_at=datetime.utcnow(),
            ),
        ]
    )
    db.commit()

    body = api("GET", "/api/llm-calls", token=auth["token"]).json()

    assert body["day"]["calls"] == 2
    assert body["day"]["success"] == 1
    assert body["day"]["fallback"] == 1
    assert body["day"]["success_rate"] == 0.5
    assert body["day"]["fallback_rate"] == 0.5
    assert body["day"]["avg_latency_ms"] == 100.0
    assert {item["prompt_id"] for item in body["by_prompt"]} == {"P12", "P03"}
    assert body["recent_total"] == 2
    assert body["recent"][0]["prompt_id"] == "P03"  # 倒序：最新在前


def test_llm_calls_only_returns_own_records(api, auth, db):
    db.add(
        LlmCall(
            user_id=auth["user"]["id"] + 99,
            prompt_id="P07",
            success=True,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    body = api("GET", "/api/llm-calls", token=auth["token"]).json()
    assert body["recent_total"] == 0
