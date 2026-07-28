"""Compound figure 1a/1b 분해 (0.2.26 · design/29)."""

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


def _rgb_png(w: int, h: int, color: tuple[int, int, int]) -> bytes:
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_status_and_pipeline() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.43"
    assert st["pipeline_version"] == "rich-v6"
    assert PIPELINE_VERSION == "rich-v6"
    assert st.get("compound_figures") is True


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


def test_split_and_expand() -> None:
    # 좌우 다른 색 — 2패널
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
    assert figs[1].caption.startswith("Fig. 1b")
    assert match_figure_index(figs, "Fig. 1a") == 0
    assert match_figure_index(figs, "Fig. 1b") == 1

    # 패널 표시 없으면 None
    assert (
        expand_compound_png(
            png, "Fig. 1. Single panel", page_index=0, id_prefix="fig", start_i=1
        )
        is None
    )


def test_design_doc() -> None:
    root = Path(__file__).resolve().parents[1]
    design = (root / "docs" / "design" / "29-compound-figures.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.26" in design
    assert "rich-v4" in design
