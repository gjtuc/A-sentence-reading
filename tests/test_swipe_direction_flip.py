"""design/143 — flip reader swipe to gallery convention."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "143-swipe-direction-flip.md"
D95 = ROOT / "docs" / "design" / "95-reader-swipe-nav.md"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_status_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.62"


def test_wiring_left_is_next() -> None:
    assert DESIGN.is_file()
    assert "0.3.59" in DESIGN.read_text(encoding="utf-8")
    assert "0.3.62" in PUB.read_text(encoding="utf-8")
    d95 = D95.read_text(encoding="utf-8")
    assert "왼쪽→다음" in d95 or "swipe left = **next**" in d95
    dart = READER.read_text(encoding="utf-8")
    assert "design/143" in dart
    # Sentence pager: negative dx → next (not previous).
    assert "final goNext = _dx < -_minDistance" in dart
    assert "final goPrev = _dx > _minDistance" in dart
    # Figure path same convention.
    assert "final goNext = dx < -_minDistance" in dart
    assert "final goPrev = dx > _minDistance" in dart
