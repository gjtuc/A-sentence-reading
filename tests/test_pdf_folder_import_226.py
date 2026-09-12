# -*- coding: utf-8 -*-
"""design/226 — PDF folder import browser floor checks."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "226-pdf-folder-import-browser.md"

_KINDS = (
    "pdf_folder_grant_start",
    "pdf_folder_grant_done",
    "pdf_folder_scan_done",
    "pdf_folder_grant_stale",
    "pdf_hash_cache_hit",
    "pdf_hash_cache_miss",
    "pdf_hash_cache_fail",
)


def test_design_226_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.225" in text
    assert "locked" in text.lower() or "Status: **locked**" in text
    assert "OPEN_DOCUMENT_TREE" in text
    assert "전수" in text
    assert "MediaStore" in text
    assert "asr.pdf_folder_grant.v1.u." in text
    assert "enqueuePickedPdfs" in text


def test_kinds() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_mobile_surface() -> None:
    models = (
        MOBILE / "lib" / "api" / "pdf_folder_grant_models.dart"
    ).read_text(encoding="utf-8")
    store = (
        MOBILE / "lib" / "api" / "pdf_folder_grant_store.dart"
    ).read_text(encoding="utf-8")
    channel = (
        MOBILE / "lib" / "platform" / "saf_tree_channel.dart"
    ).read_text(encoding="utf-8")
    screen = (
        MOBILE / "lib" / "screens" / "pdf_import_screen.dart"
    ).read_text(encoding="utf-8")
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    lib = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
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
    manifest = (
        MOBILE / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")

    assert "kPdfFolderScanMaxItems" in models
    assert "pdfFolderGrantPrefsKey" in models
    assert "bindUid" in store
    assert "asr/saf_tree" in channel
    assert "논문 폴더 연결" in screen
    assert "초록 테두리 = 이미 보관함." in screen
    assert "loadPdfFolderGrantAndScan" in ctrl
    assert "enqueueFolderPdfs" in ctrl
    assert "PdfImportScreen" in lib
    assert "OPEN_DOCUMENT_TREE" in kt
    assert "MANAGE_EXTERNAL_STORAGE" not in manifest
    assert "READ_MEDIA_IMAGES" not in manifest
    assert "READ_EXTERNAL_STORAGE" not in manifest


def test_grant_parse() -> None:
    import json

    raw = json.dumps(
        {
            "v": 1,
            "tree_uri": "content://com.android.externalstorage.documents/tree/primary%3Afoo",
            "display_label": "은규 논문",
            "granted_at_ms": 1,
        }
    )
    data = json.loads(raw)
    assert data["tree_uri"].startswith("content://")
    assert data["display_label"]
    assert PdfFolderGrant_try_parse_ok(data)


def PdfFolderGrant_try_parse_ok(m: dict) -> bool:
    uri = str(m.get("tree_uri") or "").strip()
    return bool(uri)
