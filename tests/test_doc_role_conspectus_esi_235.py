# -*- coding: utf-8 -*-
"""design/235 — CONSPECTUS chrome veto + RSC ESI footnote veto."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.pdf.supplementary_detect import detect_doc_role_detailed

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "doc_role"
DESIGN = ROOT / "docs" / "design" / "235-doc-role-conspectus-esi-footnote-veto.md"
DART = ROOT / "mobile" / "lib" / "pdf" / "doc_role_detect.dart"
CACHE = ROOT / "mobile" / "lib" / "api" / "pdf_advisory_cache_store.dart"


def _load(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def test_design_235_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.232" in text and "locked" in text.lower()
    assert "CONSPECTUS" in text
    assert "head_marker_esi_footnote_veto" in text


def test_fixture_k_conspectus_chrome_veto() -> None:
    det = detect_doc_role_detailed(
        _load("K_acs_conspectus_chrome.txt"),
        filename="bimetallic.pdf",
    )
    assert det.role == "main"
    assert det.reason == "head_marker_acs_chrome_veto"
    assert det.marker_hit is True


def test_fixture_l_rsc_esi_footnote_veto() -> None:
    det = detect_doc_role_detailed(
        _load("L_rsc_esi_footnote.txt"),
        filename="d4se00467a.pdf",
    )
    assert det.role == "main"
    assert det.reason == "head_marker_esi_footnote_veto"
    assert det.marker_hit is True


def test_fixture_d_rsc_esi_cover_still_si() -> None:
    det = detect_doc_role_detailed(_load("D_rsc_esi.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_fixture_j_chrome_without_body_still_si() -> None:
    """229: chrome without ABSTRACT/CONSPECTUS must not veto."""
    det = detect_doc_role_detailed(_load("J_chrome_no_abstract.txt"))
    assert det.role == "supplementary"
    assert det.reason == "head_marker"


def test_dart_and_cache_v4() -> None:
    dart = DART.read_text(encoding="utf-8")
    assert "CONSPECTUS" in dart
    assert "head_marker_esi_footnote_veto" in dart
    cache = CACHE.read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema = 6" in cache
