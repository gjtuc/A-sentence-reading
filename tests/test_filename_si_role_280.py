"""design/280 — filename SI hint alone → supplementary (Dart+Python twin)."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.pdf.supplementary_detect import detect_doc_role_detailed

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/280-filename-si-role.md"
DETECT = ROOT / "mobile/lib/pdf/doc_role_detect.dart"
CACHE = ROOT / "mobile/lib/api/pdf_advisory_cache_store.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"
FIXTURE_ACS_MAIN = ROOT / "tests/fixtures/doc_role/A_acs_main_chrome.txt"


def test_design_280_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.275" in text
    assert "filename_si" in text
    assert "empty" in text.lower()


def test_versions_280() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.275"' in app
    assert '"version": "0.3.275"' in app
    assert "0.3.275" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.275" in CONFIG.read_text(encoding="utf-8")
    assert "280-filename-si-role.md" in README.read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema = 16" in CACHE.read_text(encoding="utf-8")
    dart = DETECT.read_text(encoding="utf-8")
    assert "filename_si" in dart
    assert "!fnHint" in dart


def test_filename_si_alone_python() -> None:
    head = (
        "Revealing the Mechanism of Multiwalled Carbon Nanotube Growth on "
        "Supported Nickel Nanoparticles by in Situ Synchrotron X-ray Diffraction\n"
    )
    det = detect_doc_role_detailed(head, filename="cs9b00733_si_001.pdf")
    assert det.role == "supplementary"
    assert det.reason == "filename_si"

    empty = detect_doc_role_detailed("", filename="cs9b00733_si_001.pdf")
    assert empty.role == "supplementary"
    assert empty.reason == "filename_si"

    main = detect_doc_role_detailed(
        head,
        filename="1-s2.0-S0272884226009739-main.pdf",
    )
    assert main.role == "main"


def test_acs_chrome_veto_skipped_when_filename_si() -> None:
    head = FIXTURE_ACS_MAIN.read_text(encoding="utf-8")
    as_main = detect_doc_role_detailed(head, filename="an1c00673.pdf")
    assert as_main.role == "main"
    assert as_main.reason == "head_marker_acs_chrome_veto"
    as_si = detect_doc_role_detailed(head, filename="cs9b00733_si_001.pdf")
    assert as_si.role == "supplementary"
    assert as_si.reason == "head_marker"


def test_docx_reason_unchanged() -> None:
    det = detect_doc_role_detailed(
        "Experimental methods.",
        filename="paper-mmc1.docx",
    )
    assert det.role == "supplementary"
    assert det.reason == "filename_si_and_docx"
