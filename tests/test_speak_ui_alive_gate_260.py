"""design/260 — Speak UI post-beat alive gate."""
from __future__ import annotations

from pathlib import Path
from asr_versions import app_version

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/260-speak-ui-post-beat-alive-gate.md"
SCREEN = ROOT / "mobile/lib/screens/shadowing_practice_screen.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_260_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.260" in text
    assert "alive()" in text or "cycle" in text


def test_versions_260() -> None:
    assert f'version="{app_version()}"' in APP.read_text(encoding="utf-8")
    assert '"version": "0.3.260"' in APP.read_text(encoding="utf-8")
    assert app_version() in PUBSPEC.read_text(encoding="utf-8")
    assert app_version() in CONFIG.read_text(encoding="utf-8")


def test_speak_alive_gate_impl() -> None:
    src = SCREEN.read_text(encoding="utf-8")
    assert "_runSpeakPhase({required int token})" in src or (
        "_runSpeakPhase({" in src and "required int token" in src
    )
    assert "cycle_cancelled" in src
    assert "_revealSpeakUi();" in src
    # Gate must precede reveal after ready beat.
    delay_i = src.find("await Future<void>.delayed(_speakMicReadyBeat)")
    reveal_i = src.find("_revealSpeakUi();", delay_i)
    cancel_i = src.find("cycle_cancelled", delay_i)
    assert delay_i > 0 and reveal_i > delay_i and cancel_i > delay_i
    assert cancel_i < reveal_i
