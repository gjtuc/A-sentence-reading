# -*- coding: utf-8 -*-
"""design/152 — supplementary split, merge, picker/fig chips contract."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_design_152_doc() -> None:
    text = (ROOT / "docs" / "design" / "152-supplementary-merge.md").read_text(
        encoding="utf-8"
    )
    assert "0.3.78" in text
    assert "rich-v24" in text
    assert "doc_role" in text
    assert "merge-supplementary" in text
    assert "fig:s1" in text or "fig:s2" in text
    assert "메인+서플먼터리" in text
    assert "supplementary_detect" in text
    assert "can_merge_supplementary" in text
