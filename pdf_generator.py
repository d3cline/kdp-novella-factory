#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KDP Production PDF Generator

Generates a KDP-ready interior PDF with:
- 5.5" x 8.5" trim size (standard novel)
- Professional margins per KDP specs
- Best available serif font (Liberation Serif / Noto Serif / Times fallback)
- Title page, copyright page, table of contents
- Chapter headings with decorative spacing
- Professional body text typography (justified, indented)
- Centered page numbers (body only)
- Scene break ornaments
- Smart typography (curly quotes, em dashes, ellipses)

Design: production-ready output from a single call.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# ReportLab import (graceful failure)
# ---------------------------------------------------------------------------

try:
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor, black
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate,
        Paragraph, Spacer, PageBreak, Flowable,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# ---------------------------------------------------------------------------
# KDP Specifications — 5.5" x 8.5" trim
# ---------------------------------------------------------------------------

TRIM_WIDTH = 5.5   # inches
TRIM_HEIGHT = 8.5   # inches

# Margins (for 151-300 page books)
# Inside (gutter): generous for comfortable binding
# Outside/Top/Bottom: generous for professional look
MARGIN_INSIDE  = 0.875  # inches — gutter side
MARGIN_OUTSIDE = 0.625  # inches
MARGIN_TOP     = 0.75   # inches
MARGIN_BOTTOM  = 0.75   # inches

# Typography
BODY_FONT_SIZE       = 11
BODY_LEADING         = 15      # ~1.36 line spacing
CHAPTER_TITLE_SIZE   = 20
CHAPTER_NUM_SIZE     = 12
BOOK_TITLE_SIZE      = 26
SUBTITLE_SIZE        = 14
AUTHOR_SIZE          = 16
PARA_INDENT          = 0.3     # inches — first-line indent
CHAPTER_DROP         = 1.8     # inches — drop from top before chapter heading
SCENE_BREAK_SPACE    = 0.25    # inches — space around scene breaks

# Page number settings
PAGE_NUM_SIZE  = 9
FRONT_MATTER_PAGES = 6  # estimate; no page numbers on these

# ---------------------------------------------------------------------------
# Font Discovery
# ---------------------------------------------------------------------------

_SYSTEM_FONT_PATHS = [
    # Liberation Serif (excellent Times-compatible, very common on Linux)
    {
        "name": "LiberationSerif",
        "regular":    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "bold":       "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "italic":     "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "bolditalic": "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
    },
    # Liberation2
    {
        "name": "LiberationSerif",
        "regular":    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        "bold":       "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
        "italic":     "/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf",
        "bolditalic": "/usr/share/fonts/truetype/liberation2/LiberationSerif-BoldItalic.ttf",
    },
    # Noto Serif
    {
        "name": "NotoSerif",
        "regular":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
        "bold":       "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf",
        "italic":     "/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf",
        "bolditalic": "/usr/share/fonts/truetype/noto/NotoSerif-BoldItalic.ttf",
    },
    # DejaVu Serif
    {
        "name": "DejaVuSerif",
        "regular":    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "bold":       "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "italic":     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "bolditalic": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
    },
    # EB Garamond (if user installed it in .data/fonts/)
    {
        "name": "EBGaramond",
        "regular":    None,  # filled at runtime
        "bold":       None,
        "italic":     None,
        "bolditalic": None,
        "_base":      ".data/fonts",
    },
]


def _find_and_register_fonts() -> str:
    """
    Find the best available serif font family and register it with ReportLab.
    Returns the font family base name to use.
    """
    if not HAS_REPORTLAB:
        return "Times-Roman"

    for entry in _SYSTEM_FONT_PATHS:
        # Handle the EB Garamond special case (relative path)
        if entry.get("_base"):
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), entry["_base"])
            entry = {
                "name": entry["name"],
                "regular":    os.path.join(base, "EBGaramond-Regular.ttf"),
                "bold":       os.path.join(base, "EBGaramond-Bold.ttf"),
                "italic":     os.path.join(base, "EBGaramond-Italic.ttf"),
                "bolditalic": os.path.join(base, "EBGaramond-BoldItalic.ttf"),
            }

        paths = [entry["regular"], entry["bold"], entry["italic"], entry["bolditalic"]]
        if not all(p and os.path.exists(p) for p in paths):
            continue

        name = entry["name"]
        try:
            pdfmetrics.registerFont(TTFont(name, entry["regular"]))
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", entry["bold"]))
            pdfmetrics.registerFont(TTFont(f"{name}-Italic", entry["italic"]))
            pdfmetrics.registerFont(TTFont(f"{name}-BoldItalic", entry["bolditalic"]))
            registerFontFamily(
                name,
                normal=name,
                bold=f"{name}-Bold",
                italic=f"{name}-Italic",
                boldItalic=f"{name}-BoldItalic",
            )
            return name
        except Exception:
            continue

    # Fallback to built-in Times (always available in ReportLab)
    return "Times-Roman"

# ---------------------------------------------------------------------------
# Smart Typography
# ---------------------------------------------------------------------------

def _smart_typography(text: str) -> str:
    """Convert straight quotes, hyphens, and dots to professional typography."""
    # Em dashes
    text = text.replace(" --- ", "\u2014")
    text = text.replace("---", "\u2014")
    text = text.replace(" -- ", " \u2014 ")
    text = text.replace("--", "\u2013")

    # Ellipses
    text = text.replace("...", "\u2026")

    # Smart double quotes
    text = re.sub(r'(^|[\s(\[{])"', r"\1\u201c", text, flags=re.MULTILINE)
    text = text.replace('"', "\u201d")

    # Smart single quotes / apostrophes
    text = re.sub(r"(^|[\s(\[{])'", r"\1\u2018", text, flags=re.MULTILINE)
    text = text.replace("'", "\u2019")

    return text


def _md_to_rl(text: str) -> str:
    """
    Convert basic Markdown to ReportLab XML paragraph markup.
    Handles: bold, italic, smart typography, XML escaping.
    """
    # XML-escape first
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    # Smart typography
    text = _smart_typography(text)

    # Bold: **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic: *text*
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)

    return text

# ---------------------------------------------------------------------------
# Chapter Content Parser
# ---------------------------------------------------------------------------

def _parse_chapter_body(content: str) -> List[Dict[str, str]]:
    """
    Parse chapter text into structured elements.
    Returns: [{type: 'paragraph'|'first_paragraph'|'scene_break', text: '...'}]
    """
    elements: List[Dict[str, str]] = []

    # Strip any leading markdown chapter heading
    content = re.sub(r"^#+\s+.*?\n", "", content.strip())
    content = re.sub(r"^Chapter\s+\d+[:\.\s].*?\n", "", content.strip(), flags=re.I)

    # Split on double newlines
    blocks = re.split(r"\n\s*\n", content.strip())

    after_break = True  # first paragraph gets no indent

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Scene break detection
        if re.match(r"^[\s\*\-\u2013\u2014]{3,}$", block) or block.strip() in (
            "***", "* * *", "---", "* * * *", "\u2042",
        ):
            elements.append({"type": "scene_break", "text": ""})
            after_break = True
            continue

        # Collapse internal newlines to spaces (within a paragraph block)
        text = " ".join(block.split("\n"))
        text = re.sub(r"\s+", " ", text).strip()

        if after_break:
            elements.append({"type": "first_paragraph", "text": text})
            after_break = False
        else:
            elements.append({"type": "paragraph", "text": text})

    return elements

# ---------------------------------------------------------------------------
# Custom Flowables
# ---------------------------------------------------------------------------

class _SceneBreak(Flowable):
    """Centered ornamental scene break: ✦   ✦   ✦"""

    def __init__(self, width: float, font_name: str = "Times-Roman"):
        super().__init__()
        self.width = width
        self.height = SCENE_BREAK_SPACE * 2 * inch
        self._font = font_name

    def draw(self):
        self.canv.saveState()
        self.canv.setFont(self._font, 10)
        self.canv.drawCentredString(
            self.width / 2,
            self.height / 2 - 4,
            "\u2726     \u2726     \u2726",
        )
        self.canv.restoreState()


class _ThinRule(Flowable):
    """A thin centered horizontal rule."""

    def __init__(self, width: float, rule_width: float = 1.5):
        super().__init__()
        self.width = width
        self.height = 12
        self.rule_width = rule_width * inch

    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(HexColor("#999999"))
        self.canv.setLineWidth(0.4)
        cx = self.width / 2
        hw = self.rule_width / 2
        self.canv.line(cx - hw, self.height / 2, cx + hw, self.height / 2)
        self.canv.restoreState()


class _BodyStartMarker(Flowable):
    """Invisible marker — tells the page-number callback where body starts."""

    def __init__(self, builder: "KDPBookBuilder"):
        super().__init__()
        self.width = 0
        self.height = 0
        self._builder = builder

    def draw(self):
        page = self.canv.getPageNumber()
        if self._builder._body_start_page == 0:
            self._builder._body_start_page = page

# ---------------------------------------------------------------------------
# KDP Book Builder
# ---------------------------------------------------------------------------

class KDPBookBuilder:
    """
    Build a production-ready KDP interior PDF.

    Usage:
        builder = KDPBookBuilder(title, author, chapters, ...)
        result = builder.build("/path/to/output.pdf")
    """

    def __init__(
        self,
        title: str,
        author: str,
        chapters: List[Dict[str, Any]],
        dedication: str = "",
        content_warnings: str = "",
        about_author: str = "",
        copyright_year: str = "2026",
    ):
        self.title = title
        self.author = author
        self.chapters = chapters
        self.dedication = dedication
        self.content_warnings = content_warnings
        self.about_author = about_author
        self.copyright_year = copyright_year

        # Page geometry (points)
        self.page_w = TRIM_WIDTH * inch
        self.page_h = TRIM_HEIGHT * inch
        self.margin_in  = MARGIN_INSIDE * inch
        self.margin_out = MARGIN_OUTSIDE * inch
        self.margin_top = MARGIN_TOP * inch
        self.margin_bot = MARGIN_BOTTOM * inch
        self.text_w = self.page_w - self.margin_in - self.margin_out

        # Font
        self.font_base = _find_and_register_fonts()

        # Page tracking
        self._body_start_page = 0

        # Styles
        self.styles = self._create_styles()

    # ---- Font helpers ----

    def _f(self, variant: str = "") -> str:
        """Return font name for variant (bold/italic/bolditalic)."""
        b = self.font_base
        if b == "Times-Roman":
            return {
                "": "Times-Roman",
                "bold": "Times-Bold",
                "italic": "Times-Italic",
                "bolditalic": "Times-BoldItalic",
            }.get(variant, "Times-Roman")
        if variant:
            return f"{b}-{variant[0].upper()}{variant[1:]}"
        return b

    # ---- Paragraph styles ----

    def _create_styles(self) -> Dict[str, ParagraphStyle]:
        s: Dict[str, ParagraphStyle] = {}

        # Body — indented
        s["body"] = ParagraphStyle(
            "Body",
            fontName=self._f(),
            fontSize=BODY_FONT_SIZE,
            leading=BODY_LEADING,
            alignment=TA_JUSTIFY,
            firstLineIndent=PARA_INDENT * inch,
            spaceBefore=0,
            spaceAfter=0,
        )

        # Body — first paragraph (no indent)
        s["body_first"] = ParagraphStyle(
            "BodyFirst",
            parent=s["body"],
            firstLineIndent=0,
        )

        # Chapter number label
        s["ch_num"] = ParagraphStyle(
            "ChNum",
            fontName=self._f(),
            fontSize=CHAPTER_NUM_SIZE,
            leading=CHAPTER_NUM_SIZE + 4,
            alignment=TA_CENTER,
            spaceAfter=4,
            textColor=HexColor("#555555"),
        )

        # Chapter title
        s["ch_title"] = ParagraphStyle(
            "ChTitle",
            fontName=self._f("bold"),
            fontSize=CHAPTER_TITLE_SIZE,
            leading=CHAPTER_TITLE_SIZE + 6,
            alignment=TA_CENTER,
            spaceAfter=30,
        )

        # Book title (title page)
        s["book_title"] = ParagraphStyle(
            "BookTitle",
            fontName=self._f("bold"),
            fontSize=BOOK_TITLE_SIZE,
            leading=BOOK_TITLE_SIZE + 10,
            alignment=TA_CENTER,
        )

        # Subtitle / tagline
        s["subtitle"] = ParagraphStyle(
            "Subtitle",
            fontName=self._f("italic"),
            fontSize=SUBTITLE_SIZE,
            leading=SUBTITLE_SIZE + 6,
            alignment=TA_CENTER,
            textColor=HexColor("#444444"),
        )

        # Author
        s["author"] = ParagraphStyle(
            "Author",
            fontName=self._f(),
            fontSize=AUTHOR_SIZE,
            leading=AUTHOR_SIZE + 6,
            alignment=TA_CENTER,
            textColor=HexColor("#333333"),
        )

        # Copyright
        s["copyright"] = ParagraphStyle(
            "Copyright",
            fontName=self._f(),
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=HexColor("#666666"),
        )

        # Dedication
        s["dedication"] = ParagraphStyle(
            "Dedication",
            fontName=self._f("italic"),
            fontSize=12,
            leading=17,
            alignment=TA_CENTER,
        )

        # TOC heading
        s["toc_heading"] = ParagraphStyle(
            "TOCHeading",
            fontName=self._f("bold"),
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=20,
        )

        # TOC entry
        s["toc_entry"] = ParagraphStyle(
            "TOCEntry",
            fontName=self._f(),
            fontSize=11,
            leading=20,
            alignment=TA_LEFT,
            leftIndent=0.5 * inch,
        )

        # About author heading
        s["about_heading"] = ParagraphStyle(
            "AboutHeading",
            fontName=self._f("bold"),
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=16,
        )

        # About author body
        s["about_body"] = ParagraphStyle(
            "AboutBody",
            fontName=self._f(),
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
        )

        return s

    # ---- Page number callback ----

    def _on_page(self, canvas, doc):
        """Draw centered page number at bottom — body pages only."""
        page = canvas.getPageNumber()
        if self._body_start_page > 0 and page >= self._body_start_page:
            visible = page - self._body_start_page + 1
            canvas.saveState()
            canvas.setFont(self._f(), PAGE_NUM_SIZE)
            canvas.drawCentredString(
                self.page_w / 2,
                self.margin_bot * 0.45,
                str(visible),
            )
            canvas.restoreState()

    # ---- Front matter ----

    def _front_matter(self) -> List:
        el: List = []

        # ── Half-title page ──
        el.append(Spacer(1, 2.5 * inch))
        el.append(Paragraph(_md_to_rl(self.title), self.styles["book_title"]))
        el.append(PageBreak())

        # ── Blank verso ──
        el.append(Spacer(1, 0.5 * inch))
        el.append(PageBreak())

        # ── Full title page ──
        el.append(Spacer(1, 2.0 * inch))
        el.append(Paragraph(_md_to_rl(self.title), self.styles["book_title"]))
        el.append(Spacer(1, 0.4 * inch))
        el.append(_ThinRule(self.text_w, 2.0))
        el.append(Spacer(1, 0.3 * inch))
        el.append(Paragraph(f"by {_md_to_rl(self.author)}", self.styles["author"]))
        el.append(PageBreak())

        # ── Copyright page ──
        el.append(Spacer(1, 4.0 * inch))
        lines = [
            f"Copyright \u00a9 {self.copyright_year} {_md_to_rl(self.author)}",
            "All rights reserved.",
            "",
            "No part of this publication may be reproduced, distributed, or transmitted "
            "in any form or by any means, including photocopying, recording, or other "
            "electronic or mechanical methods, without the prior written permission of "
            "the author, except for brief quotations in reviews.",
        ]
        if self.content_warnings:
            lines += ["", f"<b>Content Note</b>: {_md_to_rl(self.content_warnings)}"]
        lines += ["", "First Edition"]
        el.append(Paragraph("<br/>".join(lines), self.styles["copyright"]))
        el.append(PageBreak())

        # ── Dedication (optional) ──
        if self.dedication.strip():
            el.append(Spacer(1, 2.8 * inch))
            el.append(Paragraph(
                f"<i>{_md_to_rl(self.dedication)}</i>",
                self.styles["dedication"],
            ))
            el.append(PageBreak())

        # ── Table of Contents ──
        el.append(Spacer(1, 1.5 * inch))
        el.append(Paragraph("Contents", self.styles["toc_heading"]))
        el.append(_ThinRule(self.text_w, 3.0))
        el.append(Spacer(1, 0.15 * inch))
        for ch in self.chapters:
            num = ch.get("chapter_num", "?")
            title = _md_to_rl(ch.get("title", ""))
            el.append(Paragraph(
                f"<b>Chapter {num}</b> &nbsp;&nbsp; {title}",
                self.styles["toc_entry"],
            ))
        el.append(PageBreak())

        return el

    # ---- Chapter rendering ----

    def _render_chapter(self, chapter: Dict[str, Any]) -> List:
        el: List = []

        ch_num = chapter.get("chapter_num", "?")
        ch_title = chapter.get("title", "")
        content = chapter.get("content", "")

        # Drop space
        el.append(Spacer(1, CHAPTER_DROP * inch))

        # Chapter number
        el.append(Paragraph(f"Chapter {ch_num}", self.styles["ch_num"]))

        # Decorative rule
        el.append(_ThinRule(self.text_w, 1.5))
        el.append(Spacer(1, 6))

        # Chapter title
        el.append(Paragraph(_md_to_rl(ch_title), self.styles["ch_title"]))

        # Body paragraphs
        parsed = _parse_chapter_body(content)
        for elem in parsed:
            if elem["type"] == "scene_break":
                el.append(_SceneBreak(self.text_w, self._f()))
            elif elem["type"] == "first_paragraph":
                el.append(Paragraph(_md_to_rl(elem["text"]), self.styles["body_first"]))
            else:
                el.append(Paragraph(_md_to_rl(elem["text"]), self.styles["body"]))

        el.append(PageBreak())
        return el

    # ---- Back matter ----

    def _back_matter(self) -> List:
        el: List = []
        if not self.about_author.strip():
            return el

        el.append(Spacer(1, 2.0 * inch))
        el.append(Paragraph("About the Author", self.styles["about_heading"]))
        el.append(_ThinRule(self.text_w, 2.0))
        el.append(Spacer(1, 0.2 * inch))
        for para in self.about_author.strip().split("\n\n"):
            para = para.strip()
            if para:
                el.append(Paragraph(_md_to_rl(para), self.styles["about_body"]))
                el.append(Spacer(1, 8))
        el.append(PageBreak())
        return el

    # ---- Build the final PDF ----

    def build(self, output_path: str) -> Dict[str, Any]:
        if not HAS_REPORTLAB:
            return {
                "ok": False,
                "error": "reportlab_not_installed",
                "message": "PDF generation requires reportlab. Install it:\n"
                           "  pip install reportlab\n"
                           "Then try again.",
            }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Document
        doc = BaseDocTemplate(
            output_path,
            pagesize=(self.page_w, self.page_h),
            title=self.title,
            author=self.author,
            leftMargin=self.margin_in,
            rightMargin=self.margin_out,
            topMargin=self.margin_top,
            bottomMargin=self.margin_bot,
        )

        # Single frame (consistent margins — suitable for KDP)
        frame = Frame(
            self.margin_in,
            self.margin_bot,
            self.text_w,
            self.page_h - self.margin_top - self.margin_bot,
            id="main",
        )
        tmpl = PageTemplate(id="main", frames=[frame], onPage=self._on_page)
        doc.addPageTemplates([tmpl])

        # Assemble all elements
        elements: List = []

        # Front matter
        elements.extend(self._front_matter())

        # Body start marker (triggers page numbering)
        elements.append(_BodyStartMarker(self))

        # Chapters
        for chapter in self.chapters:
            elements.extend(self._render_chapter(chapter))

        # Back matter
        elements.extend(self._back_matter())

        # Render
        doc.build(elements)

        # Stats
        fsize = os.path.getsize(output_path)
        total_words = sum(ch.get("word_count", 0) for ch in self.chapters)

        return {
            "ok": True,
            "path": os.path.abspath(output_path),
            "file_size": fsize,
            "file_size_human": f"{fsize / 1024:.0f} KB" if fsize < 1048576 else f"{fsize / 1048576:.1f} MB",
            "font_used": self.font_base,
            "chapters": len(self.chapters),
            "total_words": total_words,
            "total_pages_est": total_words // 275 if total_words else 0,
            "trim_size": f'{TRIM_WIDTH}" x {TRIM_HEIGHT}"',
        }

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pdf(
    title: str,
    author: str,
    chapters: List[Dict[str, Any]],
    output_path: str,
    dedication: str = "",
    content_warnings: str = "",
    about_author: str = "",
    copyright_year: str = "2026",
) -> Dict[str, Any]:
    """
    Generate a production-ready KDP interior PDF.

    Parameters
    ----------
    title : str          Book title
    author : str         Author name
    chapters : list      List of dicts: {chapter_num, title, content, word_count?}
    output_path : str    Where to write the PDF
    dedication : str     Optional dedication text
    content_warnings : str  Optional content note for copyright page
    about_author : str   Optional about-the-author text
    copyright_year : str Copyright year

    Returns
    -------
    dict with ok, path, file_size, font_used, chapters, total_words, etc.
    """
    builder = KDPBookBuilder(
        title=title,
        author=author,
        chapters=chapters,
        dedication=dedication,
        content_warnings=content_warnings,
        about_author=about_author,
        copyright_year=copyright_year,
    )
    return builder.build(output_path)


# ---------------------------------------------------------------------------
# CLI (standalone usage)
# ---------------------------------------------------------------------------

def main():
    """Quick test: generate a sample PDF."""
    import json as _json

    if len(sys.argv) < 2:
        print("Usage: python3 pdf_generator.py <meta.json> <chapters.json> <output.pdf>")
        print("   Or: python3 pdf_generator.py --test  (generate a test PDF)")
        sys.exit(1)

    if sys.argv[1] == "--test":
        # Generate a test PDF with sample content
        sample_chapters = [
            {
                "chapter_num": 1,
                "title": "The Beginning",
                "content": (
                    "It started the way most things start in a small town\u2014slowly, then all at once.\n\n"
                    "I was seventeen the summer everything changed. The kind of seventeen where you think "
                    "you know everything but really you\u2019re just a kid wearing your dad\u2019s shoes, "
                    "hoping nobody notices they\u2019re two sizes too big.\n\n"
                    "* * *\n\n"
                    "The morning it happened, I remember the smell of coffee drifting up the stairs. "
                    "Mom was already in the kitchen, the way she always was, standing at the counter "
                    "with that old blue mug\u2014the one with the chip on the handle that she refused "
                    "to throw away.\n\n"
                    "\u201cYou\u2019re up early,\u201d she said without turning around.\n\n"
                    "\u201cCouldn\u2019t sleep.\u201d\n\n"
                    "She turned then, and I could see she hadn\u2019t slept either. Her eyes had that "
                    "look\u2014the one I\u2019d come to recognize later as the look of someone carrying "
                    "a secret too heavy for one person."
                ),
                "word_count": 178,
            },
            {
                "chapter_num": 2,
                "title": "What Came Before",
                "content": (
                    "To understand what happened that summer, you have to understand where I came from.\n\n"
                    "Our town sat at the edge of the Ozarks, one of those places that time forgot on purpose. "
                    "Population 2,400, give or take whoever had left for good that month. We had a gas station, "
                    "a library the size of a living room, and three churches for a town that probably needed "
                    "therapy more than it needed Jesus.\n\n"
                    "I\u2019m not saying that to be funny. I\u2019m saying it because it\u2019s true.\n\n"
                    "* * *\n\n"
                    "My father was a mechanic. Not the kind you see in movies\u2014no philosophical monologues "
                    "about engines and life. He was the kind who came home with grease under his nails and "
                    "didn\u2019t talk much at dinner."
                ),
                "word_count": 149,
            },
        ]

        result = generate_pdf(
            title="Small Town Secrets",
            author="Jane Doe",
            chapters=sample_chapters,
            output_path="test_kdp_output.pdf",
            dedication="For everyone who made it out.\nAnd for those still trying.",
            content_warnings="This book contains depictions of family dysfunction and rural poverty.",
            about_author="Jane Doe grew up in the rural Midwest and now lives in Portland, Oregon. "
                         "This is her first book.",
        )
        print(_json.dumps(result, indent=2))
    else:
        # Load from files
        meta_path = sys.argv[1]
        chapters_path = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else "output.pdf"

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = _json.load(f)
        with open(chapters_path, "r", encoding="utf-8") as f:
            chapters = _json.load(f)

        result = generate_pdf(
            title=meta.get("title", "Untitled"),
            author=meta.get("author", "Anonymous"),
            chapters=chapters,
            output_path=output_path,
            dedication=meta.get("dedication", ""),
            content_warnings=meta.get("content_warnings", ""),
            about_author=meta.get("about_author", ""),
            copyright_year=meta.get("copyright_year", "2026"),
        )
        print(_json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
