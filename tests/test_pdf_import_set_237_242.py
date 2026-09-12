# -*- coding: utf-8 -*-
"""design/237-242 — PDF import DOI find, pick/copy, set rows, library pair, find-watch."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGNS = ROOT / "docs" / "design"

EV_DART = MOBILE / "lib" / "services" / "evidence_kinds.dart"
EV_PY = ROOT / "src" / "sentence_reading" / "llm" / "evidence_kinds.py"
CACHE = MOBILE / "lib" / "api" / "pdf_advisory_cache_store.dart"
MODELS = MOBILE / "lib" / "api" / "pdf_folder_grant_models.dart"
SCREEN = MOBILE / "lib" / "screens" / "pdf_import_screen.dart"
SAF_DART = MOBILE / "lib" / "platform" / "saf_tree_channel.dart"
SAF_KT = (
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
)
PAIR_DART = MOBILE / "lib" / "pdf" / "normalize_pairing_key.dart"
PAPER = MOBILE / "lib" / "api" / "paper_models.dart"
LIB_UI = MOBILE / "lib" / "screens" / "library_screen.dart"
CTRL = MOBILE / "lib" / "state" / "library_controller.dart"
APP = ROOT / "src" / "sentence_reading" / "api" / "app.py"
PUBSPEC = MOBILE / "pubspec.yaml"
CONFIG = MOBILE / "lib" / "config.dart"

KINDS = [
    "pdf_advisory_doi_hit",
    "pdf_advisory_doi_miss",
    "pdf_import_find_open",
    "pdf_import_find_fail",
    "pdf_import_pick_start",
    "pdf_import_pick_done",
    "pdf_folder_rescan_done",
    "pdf_import_set_built",
    "pdf_import_set_enqueue",
    "pdf_tree_write_probe",
    "pdf_tree_copy_start",
    "pdf_tree_copy_done",
    "pdf_tree_copy_fail",
    "pdf_find_watch_arm",
    "pdf_find_watch_hit",
    "pdf_find_watch_timeout",
    "pdf_find_watch_confirm",
    "pdf_find_watch_disarm",
]


def test_designs_237_242_locked() -> None:
    for _n, stem in [
        (237, "237-pdf-import-doi-find-cta.md"),
        (238, "238-pdf-import-open-document-pick.md"),
        (239, "239-pdf-import-advisory-set-pairing.md"),
        (240, "240-library-paired-set-row.md"),
        (241, "241-saf-tree-write-copy.md"),
        (242, "242-pdf-import-find-watch.md"),
    ]:
        text = (DESIGNS / stem).read_text(encoding="utf-8")
        assert "0.3.235" in text
        assert "locked" in text.lower()


def test_versions_current() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.' in app
    assert '"version": "0.3.' in app
    assert "0.3." in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3." in CONFIG.read_text(encoding="utf-8")


def test_cache_schema_v7() -> None:
    cache = CACHE.read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema = 8" in cache
    assert "advisory_doi" in cache
    assert "doi_source" in cache


def test_scanned_entry_has_advisory_doi() -> None:
    models = MODELS.read_text(encoding="utf-8")
    assert "advisoryDoi" in models
    assert "PdfImportSetItem" in models or "buildPdfImportListItems" in models


def test_surface_strings() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    assert "SI 찾아보기" in screen
    assert "메인 찾아보기" in screen
    assert "다운로드에서 가져오기" in screen or "받은 PDF 고르기" in screen
    assert "SI 없음" in screen
    assert "fetchMateForEntry" in screen
    assert ("doi.org" in screen or "fetchMateForEntry" in screen)
    assert "LaunchMode.externalApplication" in screen
    assert "armFindWatch" in screen
    lib = LIB_UI.read_text(encoding="utf-8")
    assert "짝과 합치기" in lib or "짝 합치기" in lib


def test_pairing_dart_exists() -> None:
    text = PAIR_DART.read_text(encoding="utf-8")
    assert "normalizePairingKey" in text
    assert "normalizeTitleKey" in text
    assert "supplementary" in text


def test_saf_tree_methods() -> None:
    kt = SAF_KT.read_text(encoding="utf-8")
    for m in (
        "probeTreeWritable",
        "copyUriIntoTree",
        "pickDocuments",
        "REQ_DOCS",
        "FLAG_GRANT_WRITE_URI_PERMISSION",
    ):
        assert m in kt, m
    dart = SAF_DART.read_text(encoding="utf-8")
    for m in ("probeTreeWritable", "copyUriIntoTree", "pickDocuments"):
        assert m in dart, m


def test_evidence_kinds_both_allowlists() -> None:
    dart = EV_DART.read_text(encoding="utf-8")
    py = EV_PY.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in dart, k
        assert k in py, k


def test_paired_cache_id_in_paper_models() -> None:
    paper = PAPER.read_text(encoding="utf-8")
    assert "paired_cache_id" in paper
    assert "pairedCacheId" in paper


def test_controller_wires_doi_and_watch() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "extractDoiFromText" in ctrl
    assert "armFindWatch" in ctrl
    assert ("pickReceivedPdfsIntoFolder" in ctrl or "importSelectedFromDownloads" in ctrl)
    assert "fetchMateForEntry" in ctrl
    assert "enqueueFolderPdfSet" in ctrl
    assert "rescanPdfFolderDebounced" in ctrl
    assert "'doi':" not in ctrl
    assert '"doi":' not in ctrl


def test_no_manage_external_storage() -> None:
    kt = SAF_KT.read_text(encoding="utf-8")
    assert "MANAGE_EXTERNAL_STORAGE" not in kt
    manifest = (
        MOBILE / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert "MANAGE_EXTERNAL_STORAGE" not in manifest


def test_polish_235_contracts() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "_pdfFindWatchIgnoreUris" in ctrl
    assert "noteFindWatchIgnore" in ctrl
    assert "copy_partial" in ctrl
    assert "refreshPdfFolderWritable" in ctrl
    assert "pdfFolderWritable" in ctrl
    assert "pairAdjacentPapers" in ctrl or "pairAdjacent" in (
        Path("mobile/lib/services/paper_disk_store.dart").read_text(encoding="utf-8")
    )
    models = MODELS.read_text(encoding="utf-8")
    assert "pairingKey" in models
    assert "matePresentForEntry" in models
    assert "effectivePairingKey" in models
    screen = SCREEN.read_text(encoding="utf-8")
    assert "onFindMain: null" in screen
    assert "matePresentForEntry" in screen
    assert "pdfFolderWritable == false" in screen
    cache = CACHE.read_text(encoding="utf-8")
    assert "pairing_key" in cache
    disk = (MOBILE / "lib" / "services" / "paper_disk_store.dart").read_text(
        encoding="utf-8"
    )
    assert "pairedCacheId" in disk
    assert "canMergeSupplementary" in disk
    assert "pairAdjacentPapers" in disk
    saf = SAF_DART.read_text(encoding="utf-8")
    assert "normalizeNfkc" in saf
    kt = SAF_KT.read_text(encoding="utf-8")
    assert "normalizeNfkc" in kt
    assert "Normalizer" in kt
