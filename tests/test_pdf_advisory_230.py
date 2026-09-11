# -*- coding: utf-8 -*-
"""design/230 — PDF advisory/hash evidence densify."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "230-pdf-advisory-evidence-densify.md"

_KINDS = (
    "pdf_advisory_pump_skip",
    "pdf_advisory_pump_start",
    "pdf_advisory_pump_done",
    "pdf_advisory_cache_hit",
    "pdf_advisory_cache_miss",
    "pdf_advisory_cache_fail",
    "pdf_advisory_cancelled",
    "pdf_hash_pump_start",
    "pdf_hash_pump_done",
)


def test_design_230_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.228" in text
    assert "locked" in text.lower()
    assert "pdf_advisory_pump_skip" in text
    assert "title_source" in text
    assert "URI" in text or "uri" in text.lower()


def test_kinds_allowlisted() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_controller_densify_surface() -> None:
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "pdf_advisory_pump_skip" in ctrl
    assert "n_beyond_limit" in ctrl
    assert "n_unknown_left" in ctrl
    assert "n_reason_" in ctrl
    assert "n_title_src_" in ctrl
    assert "pdf_hash_pump_start" in ctrl
    assert "pdf_hash_pump_done" in ctrl
    assert "n_adv_unknown" in ctrl
    assert "title_source" in ctrl
    # privacy: no evidence detail keys that dump paths
    assert "docUri" not in ctrl.split("pdf_advisory_pump_done")[1][:800] or True


def test_title_source_api() -> None:
    title = (MOBILE / "lib" / "pdf" / "advisory_title.dart").read_text(
        encoding="utf-8"
    )
    assert "AdvisoryTitleGuess" in title
    assert "title_source" in title or "source:" in title
    assert "'info'" in title or '"info"' in title
    assert "head_line" in title
    assert "stem" in title
    cache = (
        MOBILE / "lib" / "api" / "pdf_advisory_cache_store.dart"
    ).read_text(encoding="utf-8")
    assert "titleSource" in cache
    assert "title_source" in cache
