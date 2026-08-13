"""Fig. N → 그림 점프 힌트 (0.2.25 · design/28)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.fig_refs import (
    caption_key,
    hints_for_sentence,
    match_figure_index,
    parse_refs,
)
from sentence_reading.models import Figure


def test_status_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.46"
    assert st.get("fig_ref_hints") is True


def test_parse_refs() -> None:
    assert parse_refs("see Fig. 2 for details.") == ["Fig. 2"]
    assert parse_refs("Figure 1 and Scheme 1a") == ["Figure 1", "Scheme 1a"]
    assert parse_refs("Table S1 shows") == ["Table S1"]
    assert parse_refs("no figures here") == []
    assert parse_refs("as in <i>Fig. 3</i> above") == ["Fig. 3"]


def test_caption_key() -> None:
    assert caption_key("Fig. 2 — XRD pattern") == "fig:2"
    assert caption_key("Scheme 1a. Reaction") == "scheme:1a"
    assert caption_key("Table S1 Summary") == "table:s1"
    assert caption_key("random caption") is None


def test_match_and_hints() -> None:
    figs = [
        Figure(id="a", image_src="x", caption="Fig. 1 — A"),
        Figure(id="b", image_src="x", caption="Fig. 2 — B"),
        Figure(id="c", image_src="x", caption="Scheme 1. C"),
    ]
    assert match_figure_index(figs, "Fig. 2") == 1
    assert match_figure_index(figs, "Scheme 1") == 2
    assert match_figure_index(figs, "Fig. 9") is None
    hints = hints_for_sentence("As shown in Fig. 2 and Scheme 1.", figs)
    assert hints == [
        {"ref": "Fig. 2", "figure_index": 1},
        {"ref": "Scheme 1", "figure_index": 2},
    ]


def test_static_and_design() -> None:
    root = Path(__file__).resolve().parents[1]
    js = (root / "src" / "sentence_reading" / "static" / "fig_refs.js").read_text(
        encoding="utf-8"
    )
    assert "hintsForSentence" in js
    html = (root / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "fig_refs.js" in html
    assert "figRefHints" in html
    design = (root / "docs" / "design" / "28-fig-ref-jump.md").read_text(encoding="utf-8")
    assert "0.2.25" in design
