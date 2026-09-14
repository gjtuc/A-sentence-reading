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


def test_design_280_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.273" in text
    assert "filename_si" in text
    assert "13 → 14" in text or "schema" in text.lower()


def test_versions_280() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.273"' in app
    assert '"version": "0.3.273"' in app
    assert "0.3.273" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.273" in CONFIG.read_text(encoding="utf-8")
    assert "280-filename-si-role.md" in README.read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema = 14" in CACHE.read_text(encoding="utf-8")
    assert "filename_si" in DETECT.read_text(encoding="utf-8")


def test_filename_si_alone_python() -> None:
    # Title-only head (typical SI cover after 277 style join) + ACS SI filename.
    head = (
        "Revealing the Mechanism of Multiwalled Carbon Nanotube Growth on "
        "Supported Nickel Nanoparticles by in Situ Synchrotron X-ray Diffraction\n"
    )
    det = detect_doc_role_detailed(head, filename="cs9b00733_si_001.pdf")
    assert det.role == "supplementary"
    assert det.reason == "filename_si"
    assert det.filename_si_hint is True

    det2 = detect_doc_role_detailed(head, filename="cs9b00733_si_001 (1).pdf")
    assert det2.role == "supplementary"
    assert det2.reason == "filename_si"

    main = detect_doc_role_detailed(
        head,
        filename="1-s2.0-S0272884226009739-main.pdf",
    )
    assert main.role == "main"
    assert main.reason == "default_main"


def test_docx_reason_unchanged() -> None:
    det = detect_doc_role_detailed(
        "Experimental methods.",
        filename="paper-mmc1.docx",
    )
    assert det.role == "supplementary"
    assert det.reason == "filename_si_and_docx"
