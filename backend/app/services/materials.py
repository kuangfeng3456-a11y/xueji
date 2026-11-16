"""资料导入：从上传文件中抽取文本，并解析成知识点树。"""

import io
import re
from typing import List, Optional, Tuple

from ..config import settings
from ..llm import llm


def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ValueError("文件超过 5MB 限制，请拆分后再上传")
    if lower.endswith((".txt", ".md", ".csv")):
        for encoding in ("utf-8", "gb18030", "utf-16"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")
    if lower.endswith(".docx"):
        try:
            import docx
        except ImportError:
            raise ValueError("服务端缺少 python-docx，无法解析 Word 文件")
        document = docx.Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(parts)
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("服务端缺少 pypdf，无法解析 PDF 文件")
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    raise ValueError("仅支持 .txt / .md / .csv / .docx / .pdf 文件")


def parse_knowledge_lines(text: str, max_points: int = 60) -> List[dict]:
    """把资料文本解析成知识点树，返回 [{name, parent, weight}]。

    支持 Markdown 标题层级与列表项；无结构文本按行拆分。
    """
    lines = [line.rstrip() for line in text.splitlines()]
    points: List[dict] = []
    seen = set()
    heading_stack: List[Tuple[int, str]] = []

    def add(name: str, parent: Optional[str], weight: float) -> None:
        name = re.sub(r"\s+", " ", name).strip(" \t-*·•:：,，.。")
        if not name or len(name) > 60:
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        points.append({"name": name, "parent": parent, "weight": weight})

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            name = heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent = heading_stack[-1][1] if heading_stack else None
            add(name, parent, 1.5 if level == 1 else 1.2)
            heading_stack.append((level, name))
            continue

        item = re.match(r"^(?:[-*•·]|\d+[.、)]|[（(]\d+[)）])\s*(.+)$", line)
        if item:
            parent = heading_stack[-1][1] if heading_stack else None
            add(item.group(1), parent, 1.0)
            continue

        chapter = re.match(r"^(第[一二三四五六七八九十百\d]+[章节部分单元]|[A-Z]\.\s*)(.+)$", line)
        if chapter:
            add(chapter.group(2), None, 1.3)
            continue

        if len(line) <= 40 and not re.search(r"[。！？；]$", line):
            parent = heading_stack[-1][1] if heading_stack else None
            add(line, parent, 1.0)

    if not points:
        for line in lines:
            add(line, None, 1.0)
    return points[:max_points]


async def extract_knowledge_points(text: str) -> Tuple[List[dict], str]:
    """优先使用大模型抽取结构化知识点，失败时回退到规则解析。"""
    text = (text or "").strip()
    if not text:
        return [], "empty"

    if llm.available:
        system = (
            "你是学习资料结构化助手。请把资料拆成两级知识点树，输出 JSON："
            '{"points":[{"name":"知识点","parent":"父级或null","weight":1.0}]}。'
            "要求：每个知识点不超过 20 字，最多 30 个，weight 取 0.5~2.0。只输出 JSON。"
        )
        data = await llm.chat_json(system, text[:6000])
        if isinstance(data, dict):
            raw_points = data.get("points")
            if isinstance(raw_points, list):
                points = []
                seen = set()
                for item in raw_points[:60]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()[:60]
                    if not name or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    parent = item.get("parent")
                    try:
                        weight = float(item.get("weight", 1.0))
                    except (TypeError, ValueError):
                        weight = 1.0
                    points.append(
                        {
                            "name": name,
                            "parent": str(parent).strip() if parent else None,
                            "weight": max(0.1, min(weight, 5.0)),
                        }
                    )
                if points:
                    return points, "llm"

    return parse_knowledge_lines(text), "rule"