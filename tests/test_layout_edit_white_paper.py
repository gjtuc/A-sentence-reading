# -*- coding: utf-8 -*-
"""Layout edit page preview — white paper under dark Theme (PdfRenderer)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KT = (
    ROOT
    / "mobile"
    / "android"
    / "app"
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "gjtuc"
    / "sentence_reading"
    / "PdfPagePreview.kt"
)
EDIT = ROOT / "mobile" / "lib" / "screens" / "figure_edit_screen.dart"
STASH = ROOT / "mobile" / "lib" / "services" / "paper_edit_stash.dart"


def test_pdf_renderer_erases_white_before_draw() -> None:
    text = KT.read_text(encoding="utf-8")
    assert "eraseColor" in text
    assert "Color.WHITE" in text
    assert "RENDER_MODE_FOR_DISPLAY" in text


def test_figure_edit_keeps_light_paper_under_image() -> None:
    text = EDIT.read_text(encoding="utf-8")
    assert "Colors.white" in text
    assert "Image.memory" in text
    # cache bust for prior transparent/black native previews
    stash = STASH.read_text(encoding="utf-8")
    assert "_wb.png" in stash
