"""design/317 — Azure fail-closed user copy + retry."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/317-azure-layout-failed-copy.md"
README = ROOT / "docs/design/README.md"
EXTRACT = ROOT / "src/sentence_reading/pdf/extract.py"
APP = ROOT / "src/sentence_reading/api/app.py"
WEB = ROOT / "src/sentence_reading/static/app.js"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
READER = ROOT / "mobile/lib/screens/reader_screen.dart"
MODELS = ROOT / "mobile/lib/api/reading_models.dart"

MSG = "그림 배치를 읽지 못했습니다. 문장은 저장됩니다. 잠시 후 재분석해 주세요."


def test_design_317_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "azure_layout_failed" in text
    assert MSG in text
    assert "ASR_FIGURE_PYMUPDF_FALLBACK" in text
    assert "317-azure-layout-failed-copy.md" in README.read_text(encoding="utf-8")


def test_extract_records_fail_closed_copy() -> None:
    src = EXTRACT.read_text(encoding="utf-8")
    assert 'AZURE_LAYOUT_FAILED_WARNING = "azure_layout_failed"' in src
    assert "AZURE_LAYOUT_FAILED_USER_MESSAGE" in src
    assert MSG in src
    assert "def apply_azure_layout_failed_warning" in src
    assert "outcome=\"azure_failed\"" in src or 'outcome="azure_failed"' in src


def test_ingest_surfaces_job_and_finish_message() -> None:
    src = APP.read_text(encoding="utf-8")
    assert "apply_azure_layout_failed_warning" in src
    assert "AZURE_LAYOUT_FAILED_WARNING in warnings" in src
    assert "AZURE_LAYOUT_FAILED_USER_MESSAGE" in src
    assert "azure_outcome" in src


def test_reader_banner_not_quality_banner() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    reader = READER.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    web = WEB.read_text(encoding="utf-8")
    assert "showAzureLayoutFailedBanner" in ctrl
    assert "showIngestQualityBanner = false" in ctrl
    assert MSG in ctrl
    assert "showAzureLayoutFailedBanner" in reader
    assert "재분석" in reader
    assert "hasAzureLayoutFailed" in models
    assert MSG in web
    assert "azure_layout_failed" in web
