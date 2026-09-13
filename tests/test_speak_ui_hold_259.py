"""design/259 — Speak UI holds Listen until mic ready beat ends."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/259-speak-ui-hold-listen-until-ready.md"
DESIGN_245 = ROOT / "docs/design/245-practice-speak-mic-prime.md"
SCREEN = ROOT / "mobile/lib/screens/shadowing_practice_screen.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_259_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.259" in text
    assert "말할 준비" in text
    assert "UI stays Listen" in text or "UI **stays Listen**" in text


def test_design_245_amended_by_259() -> None:
    text = DESIGN_245.read_text(encoding="utf-8")
    assert "259" in text
    assert "말할 준비" in text


def test_versions_259() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.259"' in app
    assert '"version": "0.3.259"' in app
    assert "0.3.259" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.259" in CONFIG.read_text(encoding="utf-8")


def test_speak_ui_hold_impl() -> None:
    src = SCREEN.read_text(encoding="utf-8")
    assert "_revealSpeakUi" in src
    assert "말할 준비" not in src
    assert "_speakMicReadyBeat" in src
    # Early Speak flip before _runSpeakPhase must be gone.
    assert "setState(() => _rhythmPhase = RhythmPhase.speak);" not in src
    # Reveal pairs phase + speaking status.
    assert "_rhythmPhase = RhythmPhase.speak;" in src
    assert "_status = '말하는 중';" in src
    assert "_focus.beginSpeak();" in src
