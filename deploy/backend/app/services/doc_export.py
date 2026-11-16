"""文档导出（文档 9.4 / E3）：周报与错题本的 Word / PDF 导出。

要求：
- 页眉 / 页脚带「AI 辅助生成」显式标识与服务提供者；
- 文件属性写入标题、提供者、内容编号（隐式标识）；
- 服务端不落盘，直接返回字节流。
"""

import io
from datetime import date
from typing import Dict, List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

AI_LABEL = "AI 辅助生成 · 学迹 AI 学习教练"
PROVIDER = "学迹 · 自适应 AI 学习教练"


def _new_docx(content_id: str, title: str) -> Document:
    document = Document()
    style = document.styles["Normal"]
    style.font.size = Pt(10.5)
    section = document.sections[0]
    header = section.header.paragraphs[0]
    header.text = AI_LABEL
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header.runs[0].font.size = Pt(8)
    footer = section.footer.paragraphs[0]
    footer.text = f"内容编号 {content_id} · 本文件包含 AI 辅助生成内容，仅供参考"
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.runs[0].font.size = Pt(8)

    props = document.core_properties
    props.title = title
    props.subject = "学迹周报导出"
    props.author = PROVIDER
    props.comments = f"AI 辅助生成；content_id={content_id}"
    props.keywords = "AI 辅助生成, 学迹, 周报"
    props.category = "AI-assisted"
    return document


def _add_table(document: Document, rows: List[tuple]) -> None:
    table = document.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = str(label)
        cells[1].text = str(value)


def build_report_docx(
    report: Dict, goal_name: str, content_id: str
) -> bytes:
    document = _new_docx(content_id, f"{goal_name} 周报 {report.get('week_start')}")
    document.add_heading(f"{goal_name} · 学习周报", level=0)
    document.add_paragraph(
        f"{report.get('week_start')} ~ {report.get('week_end')}"
    )
    _add_table(
        document,
        [
            ("完成率", f"{round((report.get('completion_rate') or 0) * 100)}%"),
            ("掌握度变化", f"{(report.get('mastery_delta') or 0) * 100:+.1f} 个百分点"),
            ("下周重点", report.get("focus") or "—"),
        ],
    )
    document.add_heading("本周复盘", level=1)
    for line in str(report.get("content") or "").split("\n"):
        if line.strip():
            document.add_paragraph(line.strip())
    document.add_paragraph("")
    document.add_paragraph(AI_LABEL).italic = True
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_mistakes_docx(
    mistakes: List[Dict], goal_name: str, content_id: str
) -> bytes:
    document = _new_docx(content_id, f"{goal_name} 错题本")
    document.add_heading(f"{goal_name} · 错题本", level=0)
    document.add_paragraph(f"共 {len(mistakes)} 道错题 · 导出于 {date.today().isoformat()}")
    table = document.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    headers = ["题目", "我的答案", "正确答案", "错因", "知识点", "日期"]
    for index, text in enumerate(headers):
        table.rows[0].cells[index].text = text
    for item in mistakes:
        cells = table.add_row().cells
        cells[0].text = str(item.get("question") or "")[:300]
        cells[1].text = str(item.get("user_answer") or "")
        cells[2].text = str(item.get("correct_answer") or "")
        cells[3].text = str(item.get("category_label") or item.get("category") or "")
        cells[4].text = str(item.get("kp_name") or "")
        cells[5].text = str(item.get("created_at") or "")[:10]
    document.add_paragraph("")
    document.add_paragraph(AI_LABEL).italic = True
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- PDF
def _register_cjk_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    name = "XuejiCJK"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    candidates = [
        (r"C:\Windows\Fonts\msyh.ttc", 0),
        (r"C:\Windows\Fonts\simhei.ttf", None),
        (r"C:\Windows\Fonts\simsun.ttc", 0),
    ]
    for path, subfont in candidates:
        try:
            if subfont is None:
                pdfmetrics.registerFont(TTFont(name, path))
            else:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=subfont))
            return name
        except Exception:  # noqa: BLE001 - 换下一个字体
            continue
    return "Helvetica"


def build_report_pdf(report: Dict, goal_name: str, content_id: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    font = _register_cjk_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("XuejiTitle", parent=styles["Title"], fontName=font, fontSize=20, leading=28)
    body_style = ParagraphStyle("XuejiBody", parent=styles["BodyText"], fontName=font, fontSize=10.5, leading=16)
    small_style = ParagraphStyle("XuejiSmall", parent=body_style, fontSize=8, textColor=colors.grey)

    buffer = io.BytesIO()

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm, AI_LABEL)
        canvas.drawString(18 * mm, 12 * mm, f"内容编号 {content_id} · 本文件包含 AI 辅助生成内容")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=f"{goal_name} 周报",
        author=PROVIDER,
        subject="学迹周报导出",
        creator=PROVIDER,
    )
    story = [
        Paragraph(f"{goal_name} · 学习周报", title_style),
        Paragraph(f"{report.get('week_start')} ~ {report.get('week_end')}", body_style),
        Spacer(1, 6 * mm),
    ]
    data = [
        ["完成率", f"{round((report.get('completion_rate') or 0) * 100)}%"],
        ["掌握度变化", f"{(report.get('mastery_delta') or 0) * 100:+.1f} 个百分点"],
        ["下周重点", report.get("focus") or "—"],
    ]
    table = Table([[Paragraph(str(a), body_style), Paragraph(str(b), body_style)] for a, b in data], colWidths=[40 * mm, 120 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("本周复盘", ParagraphStyle("h2", parent=body_style, fontSize=14, leading=20)))
    for line in str(report.get("content") or "").split("\n"):
        if line.strip():
            story.append(Paragraph(line.strip(), body_style))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(AI_LABEL, small_style))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
