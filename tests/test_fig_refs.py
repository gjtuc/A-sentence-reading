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
    assert st["version"] == "0.3.109"
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
        Figure(id="b", image_src="x", caption="Fig. 2 — B", slot_key="fig:2"),
        Figure(id="c", image_src="x", caption="Scheme 1. C"),
        Figure(id="d", image_src="x", caption="Fig. S2 — SI", slot_key="fig:s2"),
    ]
    assert match_figure_index(figs, "Fig. 2") == 1
    assert match_figure_index(figs, "Scheme 1") == 2
    assert match_figure_index(figs, "Fig. 9") is None
    assert match_figure_index(figs, "Fig. S2") == 3
    assert match_figure_index(figs, "S2", supplementary_merged=True) == 3
    hints = hints_for_sentence("As shown in Fig. 2 and Scheme 1.", figs)
    assert hints == [
        {"ref": "Fig. 2", "figure_index": 1},
        {"ref": "Scheme 1", "figure_index": 2},
    ]
    merged_hints = hints_for_sentence(
        "See S2 for details.", figs, supplementary_merged=True
    )
    assert merged_hints == [{"ref": "S2", "figure_index": 3}]


def test_panel_fallback_design_164() -> None:
    figs = [
        Figure(id="a", image_src="x", caption="Fig. 1a — sub"),
        Figure(id="b", image_src="x", caption="Figure 6. XPS spectra"),
    ]
    assert parse_refs("(Figure 6C) and (Figure 6D)") == ["Figure 6"]
    assert match_figure_index(figs, "Figure 6C") == 1
    assert match_figure_index(figs, "Figure 6(C)") == 1
    hints = hints_for_sentence(
        "signals (Figure 6C) and (Figure 6D) peaks.", figs
    )
    assert hints == [{"ref": "Figure 6", "figure_index": 1}]
    # Compound 1a unchanged — exact slot when present.
    assert match_figure_index(figs, "Figure 1a") == 0
    assert parse_refs("Figure 1a") == ["Figure 1a"]


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
