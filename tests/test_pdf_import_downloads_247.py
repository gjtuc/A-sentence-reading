# -*- coding: utf-8 -*-
"""design/247 — Downloads DocumentsContract hint + resume pick offer."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KT = (
    ROOT
    / "mobile/android/app/src/main/kotlin/com/gjtuc/sentence_reading/SafTreeHandler.kt"
)
SCREEN = ROOT / "mobile/lib/screens/pdf_import_screen.dart"
DESIGN = ROOT / "docs/design/247-pdf-import-downloads-bridge.md"


def test_design_247_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.238" in text
    assert "locked" in text.lower()
    assert "DocumentsContract" in text
    assert "MediaStore" in text


def test_kt_downloads_documents_contract_not_mediastore() -> None:
    kt = KT.read_text(encoding="utf-8")
    assert "downloadsDocumentUri" in kt
    assert "downloadsTreeUri" in kt
    assert "buildDocumentUri" in kt
    assert "buildTreeDocumentUri" in kt
    assert "primary:Download" in kt
    assert "MediaStore.Downloads" not in kt
    assert "downloadsInitialUri" not in kt


def test_resume_offer_pick_after_find() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    assert "_maybeOfferDownloadsPickAfterFind" in screen
    assert "_findWatchPickOffered" in screen
    assert "다운로드에서 가져올까요?" in screen
    assert "role == 'supplementary' ? '메인 찾아보기' : 'SI 찾아보기'" in screen
