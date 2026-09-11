# -*- coding: utf-8 -*-
"""design/231 — advisory PdfBox maxReadBytes 50MB (too_large fix)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "231-pdf-advisory-head-read-limit.md"
DESIGN228 = ROOT / "docs" / "design" / "228-pdf-folder-advisory-preview.md"


def test_design_231_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.229" in text
    assert "locked" in text.lower()
    assert "50MB" in text or "50 MB" in text
    assert "too_large" in text
    d228 = DESIGN228.read_text(encoding="utf-8")
    assert "50MB" in d228
    assert "231" in d228


def test_defaults_are_50mb() -> None:
    dart = (MOBILE / "lib" / "platform" / "saf_tree_channel.dart").read_text(
        encoding="utf-8"
    )
    assert "extractPdfHead" in dart
    assert "50 * 1024 * 1024" in dart
    # default arg line must not still be 2MB
    chunk = dart.split("extractPdfHead", 1)[1][:500]
    assert "50 * 1024 * 1024" in chunk
    assert "2 * 1024 * 1024" not in chunk
    kt = (
        MOBILE
        / "android"
        / "app"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "gjtuc"
        / "sentence_reading"
        / "SafTreeHandler.kt"
    ).read_text(encoding="utf-8")
    assert "50 * 1024 * 1024" in kt
    assert 'maxReadBytes") ?: (2 * 1024 * 1024)' not in kt
