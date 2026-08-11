# -*- coding: utf-8 -*-
"""design/115 — reader clip without decoration must not blank the body."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "115-reader-clip-without-decoration.md"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_design_version_and_cliprect_fix():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.29" in text
    assert "ClipRect" in text
    src = READER.read_text(encoding="utf-8")
    # WHY: regression — bare clipBehavior on AnimatedContainer blanked reader.
    assert "ClipRect(" in src
    assert "design/115" in src
    # EDGE: Card may still use clipBehavior; panels must not use Clip.hardEdge.
    assert "clipBehavior: Clip.hardEdge" not in src
    assert "0.3.29" in PUB.read_text(encoding="utf-8")
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.29"
