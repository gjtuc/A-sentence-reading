# -*- coding: utf-8 -*-
"""design/227+228 — recent label + advisory title/SI floor checks."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN227 = ROOT / "docs" / "design" / "227-pdf-import-recent-label.md"
DESIGN228 = ROOT / "docs" / "design" / "228-pdf-folder-advisory-preview.md"

_KINDS = (
    "pdf_advisory_pump_start",
    "pdf_advisory_pump_done",
    "pdf_advisory_cache_hit",
    "pdf_advisory_cache_miss",
    "pdf_advisory_cache_fail",
    "pdf_advisory_cancelled",
)


def test_design_227_228_locked() -> None:
    a = DESIGN227.read_text(encoding="utf-8")
    b = DESIGN228.read_text(encoding="utf-8")
    assert "0.3.226" in a and "locked" in a.lower()
    assert "최근" in a
    assert "0.3.226" in b and "locked" in b.lower()
    assert "추정 · 업로드 후 확정" in b
    assert "enqueue" in b.lower()
    assert "PdfBox" in b or "PdfBox-Android" in b


def test_kinds() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_mobile_surface() -> None:
    screen = (
        MOBILE / "lib" / "screens" / "pdf_import_screen.dart"
    ).read_text(encoding="utf-8")
    detect = (MOBILE / "lib" / "pdf" / "doc_role_detect.dart").read_text(
        encoding="utf-8"
    )
    title = (MOBILE / "lib" / "pdf" / "advisory_title.dart").read_text(
        encoding="utf-8"
    )
    channel = (
        MOBILE / "lib" / "platform" / "saf_tree_channel.dart"
    ).read_text(encoding="utf-8")
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    gradle = (
        MOBILE / "android" / "app" / "build.gradle.kts"
    ).read_text(encoding="utf-8")
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
        / "PdfHeadExtract.kt"
    ).read_text(encoding="utf-8")

    # design/232 — recent strip removed from PdfImportScreen
    assert "_RecentStrip" not in screen
    assert "추정 · 업로드 후 확정" in screen
    assert "추정 SI" in screen
    assert "추정 메인" in screen
    assert "detectDocRoleDetailed" in detect
    assert "empty_head" in detect
    assert "guessAdvisoryTitle" in title
    assert "extractPdfHead" in channel
    assert "ensureVisiblePdfAdvisories" in ctrl
    assert "enqueueFolderPdfs" in ctrl
    assert "displayName" in ctrl  # wire name
    assert "pdfbox-android" in gradle
    assert "PDFTextStripper" in kt
