"""design/151 — mobile figure edit overlay wiring."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"


def test_mobile_figure_edit_dart_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.125" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "fetchLayoutMap" in client
    assert "fetchSlotPlan" in client
    assert "assignSlot" in client
    assert "renderSlot" in client
    assert "fetchPagePreview" in client
    assert "fetchPaperSourceBytes" in client
    assert "commitFigureEdit" in client
    assert "/layout_map" in client
    overlay = (MOBILE / "lib" / "widgets" / "layout_overlay.dart").read_text(
        encoding="utf-8"
    )
    assert "LayoutOverlay" in overlay
    assert "LayoutBoxView" in overlay
    screen = (MOBILE / "lib" / "screens" / "figure_edit_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "FigureEditScreen" in screen
    assert "InteractiveViewer" in screen
    assert "본문에 추가" in screen
    reader = (MOBILE / "lib" / "screens" / "reader_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "FigureEditScreen" in reader
    assert "onLongPressEdit" in reader
