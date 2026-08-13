# -*- coding: utf-8 -*-
"""design/117 — figure swipe only after one-finger pan."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "117-figure-swipe-one-finger.md"
GATE = ROOT / "mobile" / "lib" / "api" / "figure_swipe_gate.dart"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_design_and_wiring():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    # Historical ship version for 117; later chips advance pubspec/status.
    assert "0.3.31" in text
    assert "one-finger" in text.lower() or "한 손가락" in text
    gate = GATE.read_text(encoding="utf-8")
    assert "allowFigureSwipeAfterPan" in gate
    assert "maxPointerCount >= 2" in gate.replace(" ", "") or (
        "maxPointerCount >= 2" in gate
    )
    src = READER.read_text(encoding="utf-8")
    assert "design/117" in src
    assert "allowFigureSwipeAfterPan" in src
    assert "_maxPointers" in src
    pub = PUB.read_text(encoding="utf-8")
    assert "0.3.49" in pub
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.50"
