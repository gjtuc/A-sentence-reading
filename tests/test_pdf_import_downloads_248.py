# -*- coding: utf-8 -*-
"""design/248 — Downloads in-app browser contracts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/248-pdf-import-downloads-inapp-browser.md"
MODELS = ROOT / "mobile/lib/api/pdf_folder_grant_models.dart"
STORE = ROOT / "mobile/lib/api/pdf_folder_grant_store.dart"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
SCREEN = ROOT / "mobile/lib/screens/pdf_import_screen.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_248_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.239" in text
    assert "locked" in text.lower()
    assert "pdf_downloads_grant" in text
    assert "pickDocuments" in text  # must say CTA does not use it


def test_versions_0_3_239() -> None:
    app = APP.read_text(encoding="utf-8")
    assert app.count('version="0.3.239"') >= 1
    assert '"version": "0.3.239"' in app
    assert "0.3.239" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.239" in CONFIG.read_text(encoding="utf-8")


def test_downloads_grant_prefs_key() -> None:
    models = MODELS.read_text(encoding="utf-8")
    assert "kPdfDownloadsGrantPrefsPrefix" in models
    assert "asr.pdf_downloads_grant.v1.u." in models
    assert "PdfImportBrowseMode" in models
    store = STORE.read_text(encoding="utf-8")
    assert "prefsPdfDownloadsGrantStore" in store
    assert "pdfDownloadsGrantPrefsKey" in store


def test_controller_open_downloads_no_pick_documents_cta() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "openDownloadsBrowse" in ctrl
    assert "importSelectedFromDownloads" in ctrl
    assert "connectPdfDownloadsFolder" in ctrl
    assert "pdfDownloadsEntries" in ctrl
    assert "pickReceivedPdfsIntoFolder" not in ctrl
    screen = SCREEN.read_text(encoding="utf-8")
    assert "SegmentedButton<PdfImportBrowseMode>" in screen
    assert "논문 폴더" in screen
    assert "다운로드" in screen
    assert "_openDownloadsBrowse" in screen
    assert "pickDocuments" not in screen
    # CTA no longer calls pickDocuments path
    assert "importSelectedFromDownloads" in screen or "_importDownloadsSelection" in screen
