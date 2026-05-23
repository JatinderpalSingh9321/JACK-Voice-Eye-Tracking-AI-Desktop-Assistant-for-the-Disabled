"""
Generate README.pdf from README.md using reportlab.
Usage: python scripts/generate_readme_pdf.py
"""

import os
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Preformatted
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(PROJECT_ROOT, "README.md")
PDF_PATH = os.path.join(PROJECT_ROOT, "README.pdf")

# ── Color Palette ─────────────────────────────────────────────────────
NAVY       = colors.HexColor("#081425")
CYAN       = colors.HexColor("#00f5c8")
LIGHT_TEXT = colors.HexColor("#d8e3fb")
DIM        = colors.HexColor("#84948d")
CARD       = colors.HexColor("#111c2d")
CARD2      = colors.HexColor("#152031")
SUCCESS    = colors.HexColor("#a3e635")
WHITE      = colors.white
BLACK      = colors.black
DARK_BG    = colors.HexColor("#0d1b2a")

def build_styles():
    styles = getSampleStyleSheet()

    base = dict(fontName="Helvetica", fontSize=10, leading=15,
                textColor=BLACK, leftIndent=0, rightIndent=0,
                spaceAfter=6, spaceBefore=3)

    s = {}

    s["title"] = ParagraphStyle("title", **{**base,
        "fontSize": 22, "leading": 28, "alignment": TA_CENTER,
        "fontName": "Helvetica-Bold", "textColor": NAVY,
        "spaceAfter": 4, "spaceBefore": 12})

    s["subtitle"] = ParagraphStyle("subtitle", **{**base,
        "fontSize": 12, "alignment": TA_CENTER,
        "textColor": colors.HexColor("#334155"),
        "spaceAfter": 2, "spaceBefore": 0})

    s["meta"] = ParagraphStyle("meta", **{**base,
        "fontSize": 10, "alignment": TA_CENTER,
        "textColor": DIM, "spaceAfter": 8})

    s["h2"] = ParagraphStyle("h2", **{**base,
        "fontSize": 15, "leading": 20,
        "fontName": "Helvetica-Bold", "textColor": NAVY,
        "spaceBefore": 14, "spaceAfter": 4,
        "borderPadding": (0, 0, 4, 0)})

    s["h3"] = ParagraphStyle("h3", **{**base,
        "fontSize": 12, "leading": 16,
        "fontName": "Helvetica-Bold", "textColor": colors.HexColor("#1e3a5f"),
        "spaceBefore": 10, "spaceAfter": 3})

    s["h4"] = ParagraphStyle("h4", **{**base,
        "fontSize": 10.5, "leading": 14,
        "fontName": "Helvetica-BoldOblique", "textColor": colors.HexColor("#334155"),
        "spaceBefore": 6, "spaceAfter": 2})

    s["body"] = ParagraphStyle("body", **{**base,
        "alignment": TA_JUSTIFY, "leading": 16})

    s["bullet"] = ParagraphStyle("bullet", **{**base,
        "leftIndent": 18, "bulletIndent": 6,
        "leading": 15, "spaceAfter": 3})

    s["bullet2"] = ParagraphStyle("bullet2", **{**base,
        "leftIndent": 34, "bulletIndent": 20,
        "leading": 14, "spaceAfter": 2, "fontSize": 9.5})

    s["code"] = ParagraphStyle("code", **{**base,
        "fontName": "Courier", "fontSize": 8.5, "leading": 12,
        "backColor": colors.HexColor("#f1f5f9"),
        "leftIndent": 12, "rightIndent": 12,
        "borderPadding": 6, "textColor": colors.HexColor("#1e293b"),
        "spaceAfter": 8, "spaceBefore": 4})

    s["toc"] = ParagraphStyle("toc", **{**base,
        "textColor": colors.HexColor("#1e3a5f"),
        "leftIndent": 16, "spaceAfter": 2, "fontSize": 9.5})

    return s


def strip_html(text):
    """Remove basic HTML tags used in the README header."""
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def clean_inline(text):
    """Convert inline markdown bold/italic/code/links to plain text."""
    # Remove links but keep text: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Bold: **text** -> text
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic: *text*
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Inline code: `text`
    text = re.sub(r'`([^`]+)`', r'<font name="Courier" size="9" color="#b45309">\1</font>', text)
    # Escape unescaped ampersands (not part of existing entities)
    text = re.sub(r'&(?!amp;|lt;|gt;|nbsp;|quot;)', '&amp;', text)
    return text


def parse_readme(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    return [l.rstrip('\n').rstrip('\r') for l in lines]


def build_pdf(lines, styles, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        title="NavTools: Assistive Gaze Tracking & Voice Assistant — README",
        author="Group No. 7 | 8th Semester Major Project 2026",
    )

    story = []
    i = 0
    in_code = False
    code_buf = []
    in_table = False
    table_rows = []

    def flush_code():
        nonlocal code_buf
        if code_buf:
            block = "\n".join(code_buf)
            story.append(Preformatted(block, styles["code"]))
            code_buf = []

    def flush_table():
        nonlocal table_rows
        if not table_rows:
            return
        # Remove separator rows (rows with only --- content)
        data = [r for r in table_rows if not all(
            re.match(r'^[-: ]+$', c.strip()) for c in r
        )]
        if not data:
            table_rows = []
            return

        col_count = max(len(r) for r in data)
        # Normalize columns
        data = [r + [''] * (col_count - len(r)) for r in data]

        # Build cell paragraphs
        cell_style = ParagraphStyle("cell", fontName="Helvetica",
                                    fontSize=9, leading=13, textColor=BLACK,
                                    leftIndent=4, rightIndent=4)
        hdr_style = ParagraphStyle("hdr", fontName="Helvetica-Bold",
                                   fontSize=9, leading=13, textColor=WHITE,
                                   leftIndent=4, rightIndent=4)

        table_data = []
        for ri, row in enumerate(data):
            cells = []
            for ci, cell in enumerate(row):
                txt = clean_inline(cell.strip().strip('|').strip())
                st = hdr_style if ri == 0 else cell_style
                try:
                    cells.append(Paragraph(txt, st))
                except Exception:
                    cells.append(Paragraph(re.sub(r'<[^>]+>', '', txt), st))
            table_data.append(cells)

        avail_w = A4[0] - 4*cm
        col_w = avail_w / col_count

        tbl = Table(table_data, colWidths=[col_w]*col_count, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#f8fafc"), colors.HexColor("#f1f5f9")]),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8))
        table_rows = []

    while i < len(lines):
        line = lines[i]

        # ── Code block toggle ──────────────────────────
        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                if in_table:
                    flush_table()
                    in_table = False
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # ── Table detection ────────────────────────────
        if line.startswith("|"):
            in_table = True
            cells = [c.strip() for c in line.split("|")[1:-1]]
            table_rows.append(cells)
            i += 1
            continue
        else:
            if in_table:
                flush_table()
                in_table = False

        # ── Skip HTML tags lines (header area) ────────
        if re.match(r'^\s*</?p', line) or re.match(r'^\s*</?h1', line):
            # Try to extract text from <h1> lines
            txt = strip_html(line)
            if txt:
                story.append(Paragraph(clean_inline(txt), styles["title"]))
                story.append(Spacer(1, 4))
            i += 1
            continue

        if re.match(r'^\s*<strong>', line):
            txt = strip_html(line)
            if txt:
                story.append(Paragraph(clean_inline(txt), styles["subtitle"]))
            i += 1
            continue

        if re.match(r'^\s*<em>', line):
            txt = strip_html(line)
            if txt:
                story.append(Paragraph(clean_inline(txt), styles["meta"]))
            i += 1
            continue

        if re.match(r'^\s*<img', line):
            i += 1
            continue

        # ── HR ────────────────────────────────────────
        if line.strip() in ("---", "***", "___"):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=1,
                                    color=colors.HexColor("#cbd5e1")))
            story.append(Spacer(1, 4))
            i += 1
            continue

        # ── Blank line ────────────────────────────────
        if not line.strip():
            story.append(Spacer(1, 4))
            i += 1
            continue

        # ── Headings ──────────────────────────────────
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            text = clean_inline(m.group(2))
            # Strip anchor links like {#anchor}
            text = re.sub(r'\{#[^}]+\}', '', text).strip()
            if level == 1:
                story.append(Paragraph(text, styles["title"]))
            elif level == 2:
                story.append(Spacer(1, 6))
                story.append(Paragraph(text, styles["h2"]))
                story.append(HRFlowable(width="100%", thickness=1,
                                        color=colors.HexColor("#e2e8f0")))
                story.append(Spacer(1, 2))
            elif level == 3:
                story.append(Paragraph(text, styles["h3"]))
            else:
                story.append(Paragraph(text, styles["h4"]))
            i += 1
            continue

        # ── Bullets (- or * or +) ─────────────────────
        m = re.match(r'^(\s*)[-*+]\s+(.*)', line)
        if m:
            indent = len(m.group(1))
            text = clean_inline(m.group(2))
            st = styles["bullet2"] if indent >= 2 else styles["bullet"]
            bullet = "•" if indent < 2 else "◦"
            try:
                story.append(Paragraph(f"{bullet} {text}", st))
            except Exception:
                story.append(Paragraph(f"• {re.sub(r'<[^>]+>','',text)}", st))
            i += 1
            continue

        # ── Numbered list ─────────────────────────────
        m = re.match(r'^(\s*)\d+\.\s+(.*)', line)
        if m:
            indent = len(m.group(1))
            text = clean_inline(m.group(2))
            st = styles["bullet2"] if indent >= 2 else styles["bullet"]
            try:
                story.append(Paragraph(f"• {text}", st))
            except Exception:
                story.append(Paragraph(f"• {re.sub(r'<[^>]+>','',text)}", st))
            i += 1
            continue

        # ── Body text ─────────────────────────────────
        text = clean_inline(line)
        if text.strip():
            try:
                story.append(Paragraph(text, styles["body"]))
            except Exception:
                story.append(Paragraph(re.sub(r'<[^>]+>', '', text), styles["body"]))
        i += 1

    # Flush remaining
    if in_code:
        flush_code()
    if in_table:
        flush_table()

    doc.build(story)
    print(f"[OK] PDF saved to: {output_path}")


if __name__ == "__main__":
    lines = parse_readme(README_PATH)
    styles = build_styles()
    build_pdf(lines, styles, PDF_PATH)
