"""design/263 — SI bibliography cut + local-merge related cite helpers."""

from __future__ import annotations

from sentence_reading.cite_refs import (
    cut_bibliography_for_sentences,
    extract_bibliography,
    filter_bibliography_sentences,
    sentence_matches_bibliography,
)
from sentence_reading.llm.debone import _process_chunk_with_guard
from sentence_reading.llm.debone_quality import chunk_kind
from sentence_reading.models import Sentence
from unittest.mock import patch


def _alumina_like_bib(n: int = 5) -> str:
    lines = [
        f"[{i}] Rakov, S.I.; Author, G.S. Journal of Materials Science "
        f"{2000 + i}, {i}, 1-{i}."
        for i in range(1, n + 1)
    ]
    return (
        "Table S1 Summary of alumina doping studies with enough prose here.\n\n"
        "References\n" + "\n".join(lines)
    )


def test_cut_bibliography_keeps_tables_drops_refs() -> None:
    full = _alumina_like_bib(5)
    cut = cut_bibliography_for_sentences(full)
    assert "Table S1" in cut
    assert "References" not in cut
    assert "Rakov" not in cut
    assert len(extract_bibliography(full)) == 5


def test_cut_bibliography_noop_when_no_numbered_refs() -> None:
    text = (
        "Supplementary Note 1. Catalytic performance details "
        + ("word " * 40)
        + "\nMethods for ammoxidation continue here."
    )
    assert cut_bibliography_for_sentences(text) == text


def test_chunk_kind_endnote_dense_is_references() -> None:
    chunk = "References\n" + "\n".join(
        f"[{i}] Rakov, S.I.; Author, G.S. Journal of Materials Science "
        f"{2000 + i}, {i}, 1-{i}."
        for i in range(1, 6)
    )
    assert chunk_kind(chunk) == "references"


def test_references_chunk_emits_no_sentences() -> None:
    chunk = "References\n" + "\n".join(
        f"[{i}] Rakov, S.I.; Author, G.S. Journal of Materials Science "
        f"{2000 + i}, {i}, 1-{i}."
        for i in range(1, 6)
    )

    class _Ctx:
        section_order = ["references"]

    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        return_value=[("should not appear", "body")],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 0, 1, "", _Ctx())
    assert pairs == []
    assert stat.kind == "references"
    assert stat.ok is True


def test_filter_bibliography_sentences() -> None:
    refs = extract_bibliography(_alumina_like_bib(3))
    sents = [
        Sentence(id="a", text="Table S1 caption stays in practice stream here."),
        Sentence(
            id="b",
            text="Rakov, S.I.; Author, G.S. Journal of Materials Science 2001, 1, 1-1.",
        ),
    ]
    out = filter_bibliography_sentences(sents, refs)
    assert len(out) == 1
    assert out[0].id == "a"
    assert sentence_matches_bibliography(sents[1].text, refs) is True
