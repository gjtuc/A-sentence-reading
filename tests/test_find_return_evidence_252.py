# -*- coding: utf-8 -*-
"""design/252 — find→browser→resume causal evidence contracts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/252-find-return-causal-evidence.md"
EV_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
EV_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
SCREEN = ROOT / "mobile/lib/screens/pdf_import_screen.dart"
VALIDATE = ROOT / "mobile/lib/mate_fetch/validate.dart"
ORCH = ROOT / "mobile/lib/mate_fetch/orchestrator.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_252_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.245" in text
    assert "locked" in text.lower()
    assert "pdf_find_watch_resume_offer" in text
    assert "skip_reason" in text
    assert "find_id" in text


def test_versions_0_3_245() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.245"' in app
    assert '"version": "0.3.245"' in app
    assert "0.3.245" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.245" in CONFIG.read_text(encoding="utf-8")


def test_kinds_mirrored() -> None:
    for path in (EV_PY, EV_DART):
        text = path.read_text(encoding="utf-8")
        assert "pdf_find_watch_resume_offer" in text


def test_snake_helpers() -> None:
    assert "mateValidateCodeSnake" in VALIDATE.read_text(encoding="utf-8")
    assert "too_large" in VALIDATE.read_text(encoding="utf-8")
    assert "mateOrchestrateModeSnake" in ORCH.read_text(encoding="utf-8")
    assert "fallback_browser" in ORCH.read_text(encoding="utf-8")


def test_mate_terminals_and_find_id() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "code': 'no_doi'" in ctrl or 'code": "no_doi"' in ctrl
    assert "mate_present" in ctrl
    assert "mateValidateCodeSnake" in ctrl
    assert "mateOrchestrateModeSnake" in ctrl
    assert "pdfFindWatchFindId" in ctrl
    assert "file_kind" in ctrl


def test_resume_offer_skip_branches() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    assert "pdf_find_watch_resume_offer" in screen
    for reason in (
        "not_armed",
        "already_hit",
        "already_offered",
        "dialog_open",
        "busy",
        "reanalyzing",
        "opening",
        "expired",
    ):
        assert reason in screen
    assert "outcome': 'offered'" in screen or "outcome: 'offered'" in screen
