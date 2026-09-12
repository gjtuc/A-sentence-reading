# -*- coding: utf-8 -*-
"""design/249 — mobile folder docx list + upload contracts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/249-mobile-folder-docx.md"
KT = (
    ROOT
    / "mobile/android/app/src/main/kotlin/com/gjtuc/sentence_reading/SafTreeHandler.kt"
)
CLIENT = ROOT / "mobile/lib/api/client.dart"
RESERVE = ROOT / "mobile/lib/api/upload_reserve_store.dart"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
SCREEN = ROOT / "mobile/lib/screens/pdf_import_screen.dart"
ROLE = ROOT / "mobile/lib/pdf/doc_role_detect.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_249_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.240" in text
    assert "locked" in text.lower()
    assert "docx" in text.lower()
    assert "PdfBox" in text or "pdfbox" in text.lower() or "no PdfBox" in text


def test_versions_0_3_240() -> None:
    app = APP.read_text(encoding="utf-8")
    assert app.count('version="0.3.240"') >= 1
    assert '"version": "0.3.240"' in app
    assert "0.3.240" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.240" in CONFIG.read_text(encoding="utf-8")


def test_kt_lists_docx() -> None:
    kt = KT.read_text(encoding="utf-8")
    assert ".docx" in kt
    assert "wordprocessingml.document" in kt
    assert "uniqueDocName" in kt
    assert "mimeForDocName" in kt


def test_client_validates_docx_pk() -> None:
    client = CLIENT.read_text(encoding="utf-8")
    assert "_validateIngestBytes" in client
    assert "_docxNameRe" in client
    assert "0x4b" in client  # PK
    assert "Word(.docx)" in client or "docx" in client


def test_reserve_preserves_docx_ext() -> None:
    text = RESERVE.read_text(encoding="utf-8")
    assert ".docx" in text
    assert "filename" in text


def test_advisory_docx_filename_path() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "_docxAdvisoryTitle" in ctrl
    assert "kind': 'docx'" in ctrl or 'kind": "docx"' in ctrl or "kind': 'docx'" in ctrl
    role = ROLE.read_text(encoding="utf-8")
    assert "mmc" in role


def test_ui_docx_chip_and_title() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    assert "논문 가져오기" in screen
    assert "'DOCX'" in screen or '"DOCX"' in screen
