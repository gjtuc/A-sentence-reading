# -*- coding: utf-8 -*-
"""design/253 — Downloads OPEN_DOCUMENT direct path contracts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/253-downloads-open-document-direct.md"
KT = (
    ROOT
    / "mobile/android/app/src/main/kotlin/com/gjtuc/sentence_reading/SafTreeHandler.kt"
)
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
SCREEN = ROOT / "mobile/lib/screens/pdf_import_screen.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_253_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.246" in text
    assert "locked" in text.lower()
    assert "OPEN_DOCUMENT" in text
    assert "primary:Download" in text


def test_versions_0_3_246() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.246"' in app
    assert '"version": "0.3.246"' in app
    assert "0.3.246" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.246" in CONFIG.read_text(encoding="utf-8")


def test_kt_open_document_pdf_docx_and_document_initial_uri() -> None:
    kt = KT.read_text(encoding="utf-8")
    assert "EXTRA_MIME_TYPES" in kt
    assert "wordprocessingml.document" in kt
    assert "application/pdf" in kt
    # pickTree uses document URI, not tree URI for INITIAL_URI
    assert "downloadsDocumentUri()" in kt
    # ensure pickTree block no longer points INITIAL_URI at downloadsTreeUri
    pick_tree = kt.split('"pickTree"')[1].split('"pickDocuments"')[0]
    assert "downloadsDocumentUri()" in pick_tree
    assert "downloadsTreeUri()" not in pick_tree
    assert ".endsWith(\".docx\")" in kt or '.endsWith(".docx")' in kt


def test_open_downloads_browse_docs_path() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "downloads_docs" in ctrl
    assert "pickDocuments" in ctrl
    assert "_importPickedDocs" in ctrl
    assert "connectPdfDownloadsFolder()" not in ctrl.split("openDownloadsBrowse")[1].split(
        "List<ScannedPdfEntry> get pdfImportActiveEntries"
    )[0]


def test_ui_copy() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    assert "다운로드에서 고르기" in screen
    assert "r.mode != 'browse'" in screen or 'r.mode != "browse"' in screen
