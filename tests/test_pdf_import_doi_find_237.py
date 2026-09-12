# -*- coding: utf-8 -*-
"""design/237 — DOI find CTA hide-when-mate + evidence contracts (0.3.235)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGNS = ROOT / "docs" / "design"

DESIGN = DESIGNS / "237-pdf-import-doi-find-cta.md"
MODELS = MOBILE / "lib" / "api" / "pdf_folder_grant_models.dart"
SCREEN = MOBILE / "lib" / "screens" / "pdf_import_screen.dart"
CTRL = MOBILE / "lib" / "state" / "library_controller.dart"
CACHE = MOBILE / "lib" / "api" / "pdf_advisory_cache_store.dart"
EV_DART = MOBILE / "lib" / "services" / "evidence_kinds.dart"
EV_PY = ROOT / "src" / "sentence_reading" / "llm" / "evidence_kinds.py"


def test_design_237_locked_235() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.235" in text
    assert "locked" in text.lower()
    assert "mate" in text.lower() or "Hide" in text or "hide" in text


def test_hide_find_when_set_or_mate() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    assert "onFindMain: null" in screen
    assert "onFindSi: null" in screen
    assert "matePresentForEntry" in screen
    models = MODELS.read_text(encoding="utf-8")
    assert "matePresentForEntry" in models
    assert "effectivePairingKey" in models


def test_doi_evidence_no_plaintext() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "extractDoiFromText" in ctrl
    assert "'doi':" not in ctrl
    assert '"doi":' not in ctrl
    assert "pdf_import_find_open" in ctrl
    dart = EV_DART.read_text(encoding="utf-8")
    py = EV_PY.read_text(encoding="utf-8")
    for k in ("pdf_advisory_doi_hit", "pdf_advisory_doi_miss", "pdf_import_find_open"):
        assert k in dart
        assert k in py


def test_cache_schema_has_doi_and_pairing() -> None:
    cache = CACHE.read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema = 8" in cache
    assert "advisory_doi" in cache
    assert "pairing_key" in cache
