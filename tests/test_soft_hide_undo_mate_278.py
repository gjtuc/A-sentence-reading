"""design/278 — soft-hide undo restores expanded mate (275 asymmetry)."""
from __future__ import annotations

from pathlib import Path
from asr_versions import app_version

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/278-soft-hide-undo-mate.md"
LIB_SCREEN = ROOT / "mobile/lib/screens/library_screen.dart"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"


def test_design_278_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.271" in text
    assert "hiddenIds" in text
    assert "paper_soft_undo" in text


def test_versions_278() -> None:
    # design/278 shipped at 0.3.271; later chips may bump further.
    app = APP.read_text(encoding="utf-8")
    assert f'version="{app_version()}"' in app
    assert "0.3." in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3." in CONFIG.read_text(encoding="utf-8")
    assert "278-soft-hide-undo-mate.md" in README.read_text(encoding="utf-8")


def test_soft_hide_returns_hidden_ids() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "design/278" in ctrl
    assert "hiddenIds: idList" in ctrl
    assert "requested_n" in ctrl
    assert "listIndex()" in ctrl
    # undo expands still-hidden mates via disk pairing
    assert "paper_soft_undo" in ctrl
    assert "hidden.contains(mate)" in ctrl


def test_snackbar_undo_uses_hidden_ids() -> None:
    src = LIB_SCREEN.read_text(encoding="utf-8")
    assert "design/278" in src
    assert "result.hiddenIds" in src
    assert "undoSoftHide(undoIds)" in src
    # Must not undo with pre-expansion selection alone.
    assert "undoSoftHide(ids)" not in src
