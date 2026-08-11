"""각주 표시 정리 (0.2.57 ship · design/49; 앱 버전은 후속 범프)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cite_refs import strip_cite_markers_for_display

ROOT = Path(__file__).resolve().parents[1]


def test_status_cite_display_clean() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.5"
    assert st["cite_display_clean"] is True
    assert st["cite_ref_open"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_strip_cite_markers_for_display() -> None:
    assert strip_cite_markers_for_display("reaction.[1]") == "reaction."
    assert strip_cite_markers_for_display("A.[1] B.[2-3]") == "A. B."
    assert strip_cite_markers_for_display("x<sup>12</sup> y") == "x y"
    # edge: invalid / rejected markers stay
    assert "[0]" in strip_cite_markers_for_display("keep[0]it")
    assert strip_cite_markers_for_display("") == ""
    assert strip_cite_markers_for_display("   ") == ""
    # HTML typography kept
    assert "<i>Ni</i>" in strip_cite_markers_for_display("<i>Ni</i> catalyst.[1]")


def test_ui_hides_cites_like_fig_chips() -> None:
    css = (ROOT / "src/sentence_reading/static/styles.css").read_text(encoding="utf-8")
    assert "cite-ref-hints" in css
    assert "cite-ref-panel" in css
    assert ".fig-ref-hints" in css
    assert "design/49" in css or "각주 칩" in css
    js = (ROOT / "src/sentence_reading/static/cite_refs.js").read_text(encoding="utf-8")
    assert "stripCiteMarkersForDisplay" in js
    app_js = (ROOT / "src/sentence_reading/static/app.js").read_text(encoding="utf-8")
    assert "stripCiteMarkersForDisplay" in app_js
    assert "stripCitesForUi" in app_js
    design = (ROOT / "docs/design/49-cite-display-clean.md").read_text(encoding="utf-8")
    assert "0.2.57" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    html = TestClient(app).get("/").text
    assert "app.js?v=0.3.5" in html
    assert "styles.css?v=0.3.5" in html
