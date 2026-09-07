# -*- coding: utf-8 -*-
"""design/177 — residual blob kind classification."""
from __future__ import annotations

from sentence_reading.llm.papers_gcs import (
    classify_paper_blob_kind,
    residual_kind_counts,
)


def test_classify_paper_blob_kind_table() -> None:
    assert classify_paper_blob_kind("users/u/papers/abc/session.json") == "session"
    assert classify_paper_blob_kind("users/u/papers/abc/figures/fig-0001.png") == "figure"
    assert classify_paper_blob_kind("users/u/papers/abc/layout_map.json") == "layout"
    assert classify_paper_blob_kind("users/u/papers/abc/slot_plan.json") == "slot"
    assert classify_paper_blob_kind("users/u/papers/abc/source.pdf") == "source"
    assert classify_paper_blob_kind("users/u/papers/abc/mystery.bin") == "other"


def test_residual_kind_counts() -> None:
    names = [
        "p/session.json",
        "p/figures/a.png",
        "p/figures/b.png",
        "p/layout_map.json",
        "p/source.docx",
        "p/weird",
    ]
    c = residual_kind_counts(names)
    assert c["n_session"] == 1
    assert c["n_figure"] == 2
    assert c["n_layout"] == 1
    assert c["n_slot"] == 0
    assert c["n_source"] == 1
    assert c["n_other"] == 1
