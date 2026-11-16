"""提示词库（P00–P18）单元测试：结构、渲染、信封校验与自检。

对应文档第六章与附录 E：19 条提示词、统一信封、变量渲染不静默。
"""

import json

import pytest

from app.prompts import library


def test_library_contains_nineteen_prompts():
    assert len(library.PROMPTS) == 19
    assert sorted(library.PROMPTS) == [f"P{i:02d}" for i in range(19)]


def test_prefix_prompt_has_no_task_parameters():
    prefix = library.get("P00")
    assert prefix["tier"] is None
    assert "学迹" in prefix["system"]
    assert prefix["user_template"] == ""


@pytest.mark.parametrize(
    "prompt_id,tier,max_tokens",
    [
        ("P01", "fast", 3000),
        ("P02", "general", 3500),
        ("P04", "reasoning", 1500),
        ("P10", "reasoning", 1200),
        ("P16", "fast", 3000),
    ],
)
def test_model_parameters_match_document(prompt_id, tier, max_tokens):
    item = library.get(prompt_id)
    assert item["tier"] == tier
    assert item["max_tokens"] == max_tokens
    assert 0 <= item["temperature"] <= 1


def test_stream_prompts_follow_document():
    streaming = [pid for pid, item in library.PROMPTS.items() if item["stream"]]
    assert streaming == ["P06", "P07", "P15"]


def test_build_messages_injects_prefix_contract_and_user_template():
    messages, meta = library.build_messages(
        "P03",
        learner_state_json={"goal": "CET4"},
        mistake_json={"id": 1},
        candidate_kps_json=[{"kp_id": "k1"}],
    )

    assert [item["role"] for item in messages] == ["system", "user"]
    system = messages[0]["content"]
    assert system.startswith(library.get("P00")["system"][:20])
    assert "<output_contract>" in system
    assert '"cause": "concept"' in system  # 契约中的示例作为 few-shot

    assert '{"goal":"CET4"}' in messages[1]["content"]
    assert meta["prompt_id"] == "P03"
    assert meta["tier"] == "fast"
    assert meta["max_tokens"] == 1200
    assert meta["used_inputs"] == ["candidate_kps_json", "learner_state_json", "mistake_json"]
    assert len(meta["hash"]) == 64


def test_text_variables_render_as_plain_text():
    messages, _ = library.build_messages(
        "P01",
        exam_name="大学英语四级",
        exam_date="2026-12-19",
        existing_kp_names_json=[],
        material_text="第一章 听力",
    )
    assert "大学英语四级" in messages[1]["content"]
    assert "第一章 听力" in messages[1]["content"]
    assert "{{" not in messages[1]["content"]


def test_missing_variable_raises_instead_of_silent_empty():
    with pytest.raises(KeyError, match="material_text"):
        library.build_messages("P01", exam_name="四级", exam_date="2026-12-19")


def test_parse_json_strict_removes_markdown_fence():
    raw = '```json\n{"data": {"ok": true}, "evidence_refs": [], "confidence": 0.5, "warnings": []}\n```'
    parsed = library.parse_json_strict(raw)
    assert parsed["data"] == {"ok": True}


def test_parse_json_strict_rejects_non_json():
    with pytest.raises(ValueError):
        library.parse_json_strict("模型今天不想输出 JSON")
    with pytest.raises(ValueError):
        library.parse_json_strict("")


def test_check_envelope_accepts_document_sample():
    sample = library.sample_output("P03")
    assert sample is not None
    assert library.check_envelope(sample) == []


def test_check_envelope_reports_missing_and_invalid_fields():
    errors = library.check_envelope(
        {"data": [], "confidence": 1.5, "warnings": "none", "extra": 1}
    )
    text = " ".join(errors)
    assert "evidence_refs" in text
    assert "data 必须是对象" in text
    assert "confidence 必须在 0–1 之间" in text
    assert "warnings 必须是数组" in text
    assert "未知字段" in text


def test_every_contract_sample_is_a_valid_envelope():
    for prompt_id in library.PROMPTS:
        sample = library.sample_output(prompt_id)
        if sample is None:
            continue
        assert library.check_envelope(sample) == [], prompt_id


def test_self_check_passes():
    assert library.self_check() == []


def test_prompt_hash_is_stable_and_content_sensitive():
    digest = library.prompt_hash("P12")
    assert digest == library.prompt_hash("P12")
    assert len(digest) == 64
    payload = json.dumps(library.get("P12")["output_contract"])
    assert payload  # 契约文本参与了哈希输入
