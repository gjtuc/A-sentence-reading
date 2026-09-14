"""design/281 — supported≠SI filename; ABSTRACT-before-SI-marker → main."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.pdf.supplementary_detect import (
    detect_doc_role_detailed,
    filename_looks_like_si,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/281-si-filename-supported-abstract-veto.md"
DETECT = ROOT / "mobile/lib/pdf/doc_role_detect.dart"
CACHE = ROOT / "mobile/lib/api/pdf_advisory_cache_store.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"


def test_design_281_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.276" in text
    assert "supported" in text
    assert "head_marker_after_abstract_veto" in text


def test_versions_281() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.276"' in app
    assert '"version": "0.3.276"' in app
    assert "0.3.276" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.276" in CONFIG.read_text(encoding="utf-8")
    assert "281-si-filename-supported-abstract-veto.md" in README.read_text(
        encoding="utf-8"
    )
    assert "kPdfAdvisoryCacheSchema = 17" in CACHE.read_text(encoding="utf-8")
    dart = DETECT.read_text(encoding="utf-8")
    assert "head_marker_after_abstract_veto" in dart
    assert "supported" in dart.lower() or "supp?(?:mat" in dart


def test_supported_filename_not_si() -> None:
    name = (
        "revealing-the-mechanism-of-multiwalled-carbon-nanotube-growth-on-"
        "supported-nickel-nanoparticles-by-in-situ-synchrotron.pdf"
    )
    assert not filename_looks_like_si(name)
    head = (
        "Revealing the Mechanism of Multiwalled Carbon Nanotube Growth on "
        "Supported Nickel Nanoparticles\nABSTRACT\nWe report…\n"
    )
    det = detect_doc_role_detailed(head, filename=name)
    assert det.role == "main"
    assert det.reason == "default_main"


def test_real_si_filenames_still_hit() -> None:
    for name in (
        "cs9b00733_si_001.pdf",
        "d4se00467a1_suppl.pdf",
        "smll71948-sup-0001-suppmat.docx",
        "1-s2.0-S0272884226009739-mmc1.docx",
        "41929_2026_1513_MOESM1_ESM.pdf",
        "fujii.som.pdf",
        "catalysts-2445767-supplementary.pdf",
    ):
        assert filename_looks_like_si(name), name


def test_abstract_before_supporting_information_is_main() -> None:
    head = (
        "Coking-Resistant Ni Nanocatalysts\n"
        "Cite This: ACS Appl. Mater. Interfaces\n"
        "ABSTRACT\n"
        "We confine Ni on BN edges.\n"
        "The characterizations can be found in the\n"
        "Supporting Information.\n"
        "3. RESULTS AND DISCUSSION\n"
    )
    det = detect_doc_role_detailed(head, filename="am2c04149.pdf")
    assert det.role == "main"
    assert det.reason == "head_marker_after_abstract_veto"


def test_si_cover_still_supplementary() -> None:
    head = (
        "S-1\n"
        "Supporting Information\n"
        "Coking-Resistant Ni Nanocatalysts\n"
        "Figure S1. Raman spectra.\n"
    )
    det = detect_doc_role_detailed(head, filename="am2c04149_si_001.pdf")
    assert det.role == "supplementary"
    assert det.reason == "head_marker"
