# -*- coding: utf-8 -*-
"""design/229 — ACS main SI-badge chrome veto."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.pdf.supplementary_detect import detect_doc_role_detailed

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "doc_role"
DESIGN = ROOT / "docs" / "design" / "229-acs-si-badge-chrome-veto.md"
DART = ROOT / "mobile" / "lib" / "pdf" / "doc_role_detect.dart"
CACHE = ROOT / "mobile" / "lib" / "api" / "pdf_advisory_cache_store.dart"


def _load(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def test_design_229_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "head_marker_acs_chrome_veto" in text
    assert "0.3.227" in text


def test_fixture_a_acs_main_chrome_veto() -> None:
    det = detect_doc_role_detailed(_load("A_acs_main_chrome.txt"), filename="acsanm.1c00673.pdf")
    assert det.role == "main"
    assert det.reason == "head_marker_acs_chrome_veto"
    assert det.marker_hit is True
    assert det.filename_si_hint is False


def test_fixture_b_acs_si_cover() -> None:
    det = detect_doc_role_detailed(_load("B_acs_si_cover.txt"), filename="an1c00673_si_001.pdf")
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_fixture_c_nature() -> None:
    det = detect_doc_role_detailed(_load("C_nature_si.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_fixture_d_rsc() -> None:
    det = detect_doc_role_detailed(_load("D_rsc_esi.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_fixture_e_abstract_alone_no_veto() -> None:
    det = detect_doc_role_detailed(_load("E_si_abstract_only.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_fixture_f_midline_main() -> None:
    det = detect_doc_role_detailed(_load("F_midline.txt"), filename="paper.pdf")
    assert det.role == "main"
    assert det.reason == "default_main"
    assert det.marker_hit is False


def test_fixture_g_zwsp_si() -> None:
    det = detect_doc_role_detailed(_load("G_zwsp_si.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"
    assert det.stripped_format is True


def test_fixture_h_filename_page_label() -> None:
    det = detect_doc_role_detailed(
        _load("H_page_label_only.txt"), filename="an1c00673_si_001.pdf"
    )
    assert det.role == "supplementary"
    assert det.reason == "filename_si_and_page_label"


def test_fixture_i_one_chrome_no_veto() -> None:
    det = detect_doc_role_detailed(_load("I_one_chrome.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_fixture_j_chrome_without_abstract_no_veto() -> None:
    det = detect_doc_role_detailed(_load("J_chrome_no_abstract.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_dart_ports_veto_reason() -> None:
    dart = DART.read_text(encoding="utf-8")
    assert "head_marker_acs_chrome_veto" in dart
    assert "Metrics" in dart and "Article" in dart and "Recommendations" in dart
    cache = CACHE.read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema" in cache
