# -*- coding: utf-8 -*-
"""design/150 — column-aware vstack composite contract."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_design_150_doc() -> None:
    text = (ROOT / "docs" / "design" / "150-figure-composite-vstack.md").read_text(
        encoding="utf-8"
    )
    assert "0.3.71" in text
    assert "rich-v18" in text
    assert "_composite_figure_png" in text
    assert "_column_x_range" in text
    assert "Co–TiO₂" in text or "Fig 1" in text
    assert "vstack" in text.lower() or "Vstack" in text
