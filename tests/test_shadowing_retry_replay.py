# -*- coding: utf-8 -*-
"""design/120 — shadowing retry speak + replay my take."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "120-shadowing-retry-replay.md"
DART = ROOT / "mobile" / "lib" / "screens" / "shadowing_practice_screen.dart"
GATE = ROOT / "mobile" / "lib" / "api" / "shadowing_retry_gate.dart"
JS = ROOT / "src" / "sentence_reading" / "static" / "shadowing_practice.js"
HTML = ROOT / "src" / "sentence_reading" / "static" / "index.html"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_design_and_wiring() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.34" in text
    assert "다시" in text
    dart = DART.read_text(encoding="utf-8")
    assert "design/120" in dart
    assert "_retrySpeak" in dart
    assert "_replayTake" in dart
    assert "다시 듣기" in dart
    assert GATE.is_file()
    assert "canReplayShadowingTake" in GATE.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert "retrySpeak" in js
    assert "replayTake" in js
    html = HTML.read_text(encoding="utf-8")
    assert 'id="shadowingPracticeRetry"' in html
    assert 'id="shadowingPracticeReplay"' in html
    assert "0.3.60" in PUB.read_text(encoding="utf-8")
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.60"
