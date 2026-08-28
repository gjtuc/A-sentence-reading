"""각주 표시 정리 (0.2.57 ship · design/49; 앱 버전은 후속 범프)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cite_refs import (
    repair_dollar_cite_artifacts,
    strip_cite_markers_for_display,
)
from sentence_reading.llm.typography import apply_glossary

ROOT = Path(__file__).resolve().parents[1]


def test_status_cite_display_clean() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.82"
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


def test_glossary_skips_bracket_cite_raw() -> None:
    """Survey formulas must not replace [8, 9] with LaTeX $1 (Co–TiO₂ QA)."""
    text = "350 million tons of carbon dioxide [8, 9]."
    bad = [{"raw": "[8, 9]", "rich": "$1"}]
    out = apply_glossary(text, formulas=bad)
    assert out == text
    assert "[8, 9]" in out


def test_strip_dollar_cite_artifacts() -> None:
    assert (
        strip_cite_markers_for_display("carbon dioxide$1.")
        == "carbon dioxide."
    )
    assert strip_cite_markers_for_display("costs $33.00 each") == "costs $33.00 each"
    assert (
        strip_cite_markers_for_display("word$^{8,9}$ end")
        == "word end"
    )


def test_strip_hybrid_bracket_dollar_cite() -> None:
    """Co–TiO₂ QA: [8, 9]$1 hybrid must not leave visible $1."""
    methane = (
        "It is estimated that 143 billion cubic meters of methane were flared in 2012 "
        "which led to the emission of 350 million tons of carbon dioxide [8, 9]$1"
    )
    assert strip_cite_markers_for_display(methane).endswith("carbon dioxide")
    assert "$1" not in strip_cite_markers_for_display(methane)
    study = (
        "Methane and carbon dioxide are major contributors to greenhouse gases (GHG's) "
        "and their sequestration and removal is the subject of major scientific study [1–4]$1"
    )
    assert strip_cite_markers_for_display(study).endswith("major scientific study")
    assert "$1" not in strip_cite_markers_for_display(study)
    assert (
        strip_cite_markers_for_display("word CO<sub>2</sub>$1 here")
        == "word CO<sub>2</sub> here"
    )


def test_repair_dollar_cite_artifacts_ingest() -> None:
    assert repair_dollar_cite_artifacts("dioxide$1.") == "dioxide."
    assert repair_dollar_cite_artifacts("price $33.00") == "price $33.00"
    assert (
        repair_dollar_cite_artifacts("carbon dioxide [8, 9]$1")
        == "carbon dioxide [8, 9]"
    )


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
    assert "app.js?v=0.3.82" in html
    assert "styles.css?v=0.3.82" in html
