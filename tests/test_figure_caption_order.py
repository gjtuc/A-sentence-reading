# -*- coding: utf-8 -*-
"""design/92 — figure caption sort key + order."""
from __future__ import annotations

from sentence_reading.pdf.extract import _caption_sort_key


def test_caption_sort_fig_before_scheme_before_table() -> None:
    caps = [
        "Table 1 Summary",
        "Fig. 2 Results",
        "Scheme 1 Route",
        "Figure 1 Overview",
        "Fig. S1 Extra",
        "Graphical abstract (p.1)",
    ]
    ordered = sorted(caps, key=_caption_sort_key)
    assert ordered[0].startswith("Graphical abstract")
    assert "Overview" in ordered[1]
    assert "Results" in ordered[2]
    assert "S1" in ordered[3] or "s1" in ordered[3].lower()
    assert ordered[4].lower().startswith("scheme")
    assert ordered[5].lower().startswith("table")


def test_caption_sort_letter_suffix() -> None:
    caps = ["Fig. 1b detail", "Fig. 1a panel", "Fig. 1 main"]
    ordered = sorted(caps, key=_caption_sort_key)
    assert "main" in ordered[0]
    assert "1a" in ordered[1].lower() or "a panel" in ordered[1].lower()
    assert "1b" in ordered[2].lower() or "b detail" in ordered[2].lower()


def test_uncaptioned_placeholder_sorts_last_among_kinds() -> None:
    assert _caption_sort_key("Table (p.3)")[0] == 3
    assert _caption_sort_key("Graphical abstract (p.1)")[0] == -1
