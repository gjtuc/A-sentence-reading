# -*- coding: utf-8 -*-
"""design/151 — layout map, slot carousel, overlay editor contract."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_design_151_doc() -> None:
    text = (ROOT / "docs" / "design" / "151-layout-map-slot-carousel.md").read_text(
        encoding="utf-8"
    )
    assert "0.3.73" in text
    assert "rich-v20" in text
    assert "layout_map.json" in text
    assert "slot_plan.json" in text
    assert "Figure 1" in text or "fig:1" in text
    assert "user_confirmed" in text
    assert "layout_overlay.dart" in text
    assert "caption_pairing" in text or "caption_classify" in text
    assert "Co–TiO₂" in text or "Co-TiO" in text
