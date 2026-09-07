"""design/183 — first matched Fig/Table chip sentence index."""

from __future__ import annotations

from sentence_reading.fig_refs import first_fig_table_chip_sentence_index
from sentence_reading.models import Figure, Sentence


def _sents(*texts: str) -> list[Sentence]:
    return [
        Sentence(id=f"s{i}", text=t, section="body")
        for i, t in enumerate(texts)
    ]


def _figs(*caps: str) -> list[Figure]:
    return [
        Figure(id=f"f{i}", image_src="", caption=c, slot_key="")
        for i, c in enumerate(caps)
    ]


def test_first_chip_index_basic() -> None:
    s = _sents(
        "Intro only cites [1].",
        "Still no figure.",
        "See Fig. 1 for XRD.",
        "Also Table 2 later.",
    )
    f = _figs("Fig. 1 — XRD", "Table 2 — data")
    assert first_fig_table_chip_sentence_index(s, f) == 2


def test_unmatched_fig_does_not_count() -> None:
    s = _sents("See Fig. 99 nowhere.", "See Fig. 1 here.")
    f = _figs("Fig. 1 — real")
    assert first_fig_table_chip_sentence_index(s, f) == 1


def test_cite_only_returns_none() -> None:
    s = _sents("Refs [1,2,3] dominate Intro.")
    f = _figs("Fig. 1 — later")
    assert first_fig_table_chip_sentence_index(s, f) is None


def test_empty_and_t_zero() -> None:
    assert first_fig_table_chip_sentence_index([], []) is None
    s = _sents("Fig. 1 opens the paper.")
    f = _figs("Fig. 1 — coverish")
    assert first_fig_table_chip_sentence_index(s, f) == 0
