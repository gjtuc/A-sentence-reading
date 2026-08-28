# -*- coding: utf-8 -*-
"""design/116 — figure pinch must not lose to parent horizontal drag."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "116-figure-pinch-vs-swipe.md"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_design_version_and_no_parent_horizontal_drag():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.30" in text
    assert "InteractiveViewer" in text or "pinch" in text.lower()
    src = READER.read_text(encoding="utf-8")
    assert "design/116" in src
    # Locate _ZoomableFigureFrameState build body: no onHorizontalDrag* there.
    start = src.find("class _ZoomableFigureFrameState")
    assert start >= 0
    # Next class or EOF
    nxt = src.find("\nclass ", start + 10)
    body = src[start : nxt if nxt > 0 else len(src)]
    assert "onHorizontalDragStart" not in body
    assert "onHorizontalDragUpdate" not in body
    assert "onHorizontalDragEnd" not in body
    assert "InteractiveViewer(" in body
    assert "panEnabled: true" in body
    pub = PUB.read_text(encoding="utf-8")
    assert "0.3.84" in pub
    st = TestClient(app).get("/api/status").json()
    assert "version" in st
