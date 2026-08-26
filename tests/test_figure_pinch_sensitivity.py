# -*- coding: utf-8 -*-
"""design/118 — figure pinch sensitivity wiring."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "118-figure-pinch-sensitivity.md"
SENS = ROOT / "mobile" / "lib" / "api" / "figure_pinch_sensitivity.dart"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_design_and_wiring() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    # Historical ship version for 118; later chips advance pubspec/status.
    assert "0.3.32" in text
    assert "1.85" in text or "확실히" in text
    sens = SENS.read_text(encoding="utf-8")
    assert "amplifyFigurePinchScale" in sens
    assert "kFigurePinchSensitivity" in sens
    assert "1.85" in sens
    src = READER.read_text(encoding="utf-8")
    assert "design/118" in src
    assert "amplifyFigurePinchScale" in src
    assert "figure_pinch_sensitivity.dart" in src
    assert "0.3.67" in PUB.read_text(encoding="utf-8")
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.67"
