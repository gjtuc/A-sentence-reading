"""Compound figure 모듈 보관 · ingest 비활성 (0.2.62 · design/44)."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from sentence_reading.api.app import app
from sentence_reading.fig_refs import match_figure_index
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.compound import (
    base_figure_label,
    choose_grid,
    detect_panel_letters,
    expand_compound_png,
    panel_caption,
    split_png_equal,
)
from sentence_reading.pdf import extract as pdf_extract


def test_status_compound_off() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.62"
    assert st["pipeline_version"] == "rich-v7"
    assert PIPELINE_VERSION == "rich-v7"
    assert st.get("compound_figures") is False


def test_extract_source_has_no_compound_call() -> None:
    src = Path(pdf_extract.__file__).read_text(encoding="utf-8")
    assert "expand_compound_png" not in src
    assert "design/44" in src


def test_detect_panels() -> None:
    assert detect_panel_letters("Fig. 1. Overview.") == []
    assert detect_panel_letters("Fig. 1. (a) XRD.") == []
    assert detect_panel_letters("Fig. 1. (a) XRD (b) SEM.") == ["a", "b"]
    assert detect_panel_letters("Fig. 2 (a–c) spectra") == ["a", "b", "c"]
    assert detect_panel_letters("Scheme 1 (a)-(d) steps") == ["a", "b", "c", "d"]


def test_labels() -> None:
    assert base_figure_label("Fig. 1. (a) x (b) y") == "Fig. 1"
    assert panel_caption("Fig. 1", "a", "Fig. 1. (a) XRD (b) SEM").startswith(
        "Fig. 1a"
    )


def test_split_and_expand_module_still_works() -> None:
    """모듈은 보관 — extract 만 안 부름."""
    left = Image.new("RGB", (100, 80), (255, 0, 0))
    right = Image.new("RGB", (100, 80), (0, 0, 255))
    im = Image.new("RGB", (200, 80))
    im.paste(left, (0, 0))
    im.paste(right, (100, 0))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    png = buf.getvalue()

    assert choose_grid(2, 200, 80) == (1, 2)
    parts = split_png_equal(png, 1, 2)
    assert len(parts) == 2

    figs = expand_compound_png(
        png,
        "Fig. 1. (a) left (b) right",
        page_index=0,
        id_prefix="fig",
        start_i=1,
    )
    assert figs is not None
    assert len(figs) == 2
    assert figs[0].caption.startswith("Fig. 1a")
    assert match_figure_index(figs, "Fig. 1a") == 0


def test_design_44_and_29() -> None:
    root = Path(__file__).resolve().parents[1]
    d44 = (root / "docs" / "design" / "44-compound-off.md").read_text(encoding="utf-8")
    assert "0.2.52" in d44
    assert "expand_compound_png" in d44 or "끊" in d44
    assert "rich-v7" in d44
    d29 = (root / "docs" / "design" / "29-compound-figures.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.26" in d29
    assert "비활성" in d29 or "44" in d29
