import asyncio
import io
import sys
import types

import pytest

from app.config import settings
from app.services import materials


def test_extract_text_plain_formats():
    assert materials.extract_text("a.txt", "中文内容".encode("utf-8")) == "中文内容"
    assert materials.extract_text("A.MD", "# 标题".encode("utf-8")) == "# 标题"
    assert materials.extract_text("a.csv", "name,value\n听力,1".encode("utf-8")).startswith("name,value")
    # gb18030 回退
    assert materials.extract_text("a.txt", "国标编码".encode("gb18030")) == "国标编码"
    # utf-16 回退
    assert materials.extract_text("a.txt", "十六位".encode("utf-16")) == "十六位"


def test_extract_text_rejects_oversize_and_unknown(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(ValueError, match="5MB"):
        materials.extract_text("a.txt", b"12345")
    with pytest.raises(ValueError, match="仅支持"):
        materials.extract_text("a.xlsx", b"data")


def test_extract_text_reads_docx_with_table():
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("第一章 听力")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "短对话"
    table.rows[0].cells[1].text = "长对话"
    buffer = io.BytesIO()
    document.save(buffer)
    text = materials.extract_text("plan.docx", buffer.getvalue())
    assert "第一章 听力" in text
    assert "短对话" in text and "长对话" in text


def test_extract_text_reads_pdf():
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    text = materials.extract_text("blank.pdf", buffer.getvalue())
    assert isinstance(text, str)


def test_extract_text_reads_pdf_via_pdfreader(monkeypatch):
    class _Page:
        def extract_text(self):
            return "第 1 页"

    class _Reader:
        def __init__(self, stream):
            self.pages = [_Page(), _Page()]

    fake = types.ModuleType("pypdf")
    fake.PdfReader = _Reader
    monkeypatch.setitem(sys.modules, "pypdf", fake)

    assert materials.extract_text("a.pdf", b"%PDF-1.4") == "第 1 页\n第 1 页"


def test_extract_text_reports_missing_optional_parsers(monkeypatch):
    monkeypatch.setitem(sys.modules, "docx", None)
    with pytest.raises(ValueError, match="python-docx"):
        materials.extract_text("a.docx", b"fake")

    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(ValueError, match="pypdf"):
        materials.extract_text("a.pdf", b"fake")


def test_parse_knowledge_lines_markdown_tree():
    text = "# 听力\n- 短对话\n- 长对话\n## 听力篇章\n1. 新闻\n## 阅读\n- 选词填空\n"
    points = materials.parse_knowledge_lines(text)
    names = [item["name"] for item in points]
    assert names[:3] == ["听力", "短对话", "长对话"]
    assert points[0]["weight"] == 1.5
    by_name = {item["name"]: item for item in points}
    assert by_name["短对话"]["parent"] == "听力"
    assert by_name["听力篇章"]["parent"] == "听力"
    assert by_name["新闻"]["parent"] == "听力篇章"
    assert by_name["选词填空"]["parent"] == "阅读"


def test_parse_knowledge_lines_chapter_and_plain_lines():
    text = "第一章 听力理解\n短对话技巧\n这是一个完整的句子，不应该成为知识点。\n\nA. 阅读训练\n"
    points = materials.parse_knowledge_lines(text)
    names = [item["name"] for item in points]
    assert "听力理解" in names
    assert "短对话技巧" in names
    assert "阅读训练" in names
    assert not any(name.startswith("这是一个") for name in names)


def test_parse_knowledge_lines_dedupes_and_limits(monkeypatch):
    text = "- 重复知识点\n- 重复知识点\n"
    assert len(materials.parse_knowledge_lines(text)) == 1

    many = "\n".join(f"- 知识点{i}" for i in range(10))
    assert len(materials.parse_knowledge_lines(many, max_points=3)) == 3

    too_long = "- " + "很" * 80
    assert materials.parse_knowledge_lines(too_long) == []


def test_parse_knowledge_lines_empty_text_returns_empty():
    assert materials.parse_knowledge_lines("   \n\n") == []


def test_extract_knowledge_points_empty_text():
    points, engine = asyncio.run(materials.extract_knowledge_points("   "))
    assert points == []
    assert engine == "empty"


def test_extract_knowledge_points_rule_fallback():
    points, engine = asyncio.run(materials.extract_knowledge_points("# 听力\n- 短对话\n- 长对话"))
    assert engine == "rule"
    assert [item["name"] for item in points] == ["听力", "短对话", "长对话"]


class _FakeLLM:
    def __init__(self, payload, available=True):
        self.payload = payload
        self.available = available

    async def chat_json(self, system, user):
        return self.payload


def test_extract_knowledge_points_uses_llm_and_clamps(monkeypatch):
    payload = {
        "points": [
            {"name": "听力", "parent": None, "weight": 9},
            {"name": "短对话", "parent": "听力", "weight": "1.5"},
            {"name": "听力", "parent": None, "weight": 1},
            {"name": "", "parent": None, "weight": 1},
            "不合法条目",
            {"name": "长对话", "parent": "听力", "weight": "bad"},
        ]
    }
    monkeypatch.setattr(materials, "llm", _FakeLLM(payload))
    points, engine = asyncio.run(materials.extract_knowledge_points("# 资料"))
    assert engine == "llm"
    assert [item["name"] for item in points] == ["听力", "短对话", "长对话"]
    assert points[0]["weight"] == 5.0
    assert points[1]["weight"] == 1.5
    assert points[2]["weight"] == 1.0


def test_extract_knowledge_points_falls_back_when_llm_empty(monkeypatch):
    monkeypatch.setattr(materials, "llm", _FakeLLM(None))
    points, engine = asyncio.run(materials.extract_knowledge_points("- 短对话"))
    assert engine == "rule"
    assert points[0]["name"] == "短对话"


def test_extract_knowledge_points_falls_back_when_payload_empty(monkeypatch):
    monkeypatch.setattr(materials, "llm", _FakeLLM({"points": []}))
    points, engine = asyncio.run(materials.extract_knowledge_points("- 短对话"))
    assert engine == "rule"
    assert points


def test_extract_knowledge_points_llm_unavailable_uses_rules(monkeypatch):
    monkeypatch.setattr(materials, "llm", _FakeLLM({"points": [{"name": "听力"}]}, available=False))
    points, engine = asyncio.run(materials.extract_knowledge_points("- 听力"))
    assert engine == "rule"
    assert points[0]["name"] == "听力"