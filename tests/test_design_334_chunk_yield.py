"""design/334 — a chunk that returns a fraction of its prose is a failure.

design/167 only caught a chunk that returned *nothing*. A chunk that handed back
one sentence out of twenty reported ok, and the rest of the section vanished with
no warning anywhere in the quality record.
"""

from __future__ import annotations

from unittest.mock import patch

from sentence_reading.llm.debone import _process_chunk_with_guard
from sentence_reading.llm.debone_quality import (
    ChunkStat,
    build_ingest_quality,
    chunk_under_yielded,
    pairs_chars,
    prose_chars,
    quality_to_warnings,
)


class _Ctx:
    section_order = ["introduction", "experimental", "results"]


def _prose(n: int) -> str:
    """n distinct sentences of real-looking prose."""
    return " ".join(
        f"The catalyst sample number {i} reached a conversion of {i} percent "
        f"under the flow conditions described above."
        for i in range(n)
    )


# ---------------------------------------------------------------- ratio helpers


def test_prose_chars_ignores_markup_and_space() -> None:
    assert prose_chars("<i>abc</i> def") == 6


def test_full_return_is_not_under_yield() -> None:
    chunk = _prose(8)
    pairs = [(s + ".", "results") for s in chunk.split(". ")]
    assert chunk_under_yielded(chunk, pairs) is False


def test_single_sentence_out_of_many_is_under_yield() -> None:
    chunk = _prose(20)
    pairs = [(chunk.split(". ")[0] + ".", "results")]
    assert chunk_under_yielded(chunk, pairs) is True


def test_citation_stripping_alone_does_not_trip_the_floor() -> None:
    """Deboning legitimately removes markers; that must stay well above the floor."""
    chunk = _prose(10) + " " + " ".join(f"[{i}]" for i in range(40))
    pairs = [(s + ".", "results") for s in _prose(10).split(". ")]
    assert chunk_under_yielded(chunk, pairs) is False


def test_empty_chunk_is_not_under_yield() -> None:
    assert chunk_under_yielded("", []) is False
    assert chunk_under_yielded("   ", None) is False


# ---------------------------------------------------------------- guard retries


def test_low_yield_retry_that_succeeds_is_kept() -> None:
    chunk = _prose(20)
    thin = [(chunk.split(". ")[0] + ".", "results")]
    full = [(s + ".", "results") for s in chunk.split(". ")]
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=[thin, full],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 2, 7, "", _Ctx())
    assert stat.low_yield is True
    assert stat.fallback is None
    assert pairs_chars(pairs) == pairs_chars(full)


def test_low_yield_falls_back_to_split_when_it_returns_more() -> None:
    chunk = _prose(20)
    thin = [(chunk.split(". ")[0] + ".", "results")]
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        return_value=thin,
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 2, 7, "", _Ctx())
    assert stat.low_yield is True
    assert stat.fallback == "split"
    # The splitter is deterministic, so it must beat the thin LLM answer.
    assert pairs_chars(pairs) > pairs_chars(thin)


def test_split_is_not_taken_when_it_returns_less() -> None:
    """Never make the output worse than what the model gave us."""
    chunk = _prose(20)
    thin = [(chunk.split(". ")[0] + ".", "results")]
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        return_value=thin,
    ), patch(
        "sentence_reading.llm.debone.fallback_split_chunk",
        return_value=[("tiny.", "results")],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 2, 7, "", _Ctx())
    assert stat.low_yield is True
    assert stat.fallback is None
    assert pairs == thin


def test_healthy_chunk_never_retries() -> None:
    chunk = _prose(10)
    full = [(s + ".", "results") for s in chunk.split(". ")]
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=[full, RuntimeError("must not retry")],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 2, 7, "", _Ctx())
    assert stat.low_yield is False
    assert stat.chars_out == pairs_chars(full)


def test_sparse_chunk_is_exempt() -> None:
    """A short chunk is allowed to return little; that is what sparse means."""
    chunk = "Figure 3. Conversion versus time."
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=[[], RuntimeError("must not retry")],
    ):
        _pairs, stat = _process_chunk_with_guard(chunk, 2, 7, "", _Ctx())
    assert stat.low_yield is False


# ---------------------------------------------------------------- reporting


def test_low_yield_reaches_the_warnings() -> None:
    stats = [
        ChunkStat(index=0, chars_in=900, sentences_out=9, ok=True, kind="substantive"),
        ChunkStat(
            index=1,
            chars_in=900,
            sentences_out=1,
            ok=True,
            kind="substantive",
            low_yield=True,
        ),
    ]
    iq = build_ingest_quality(
        raw_text="alpha beta gamma",
        sentences=[],
        chunk_stats=stats,
        ungrounded_ids=[],
    )
    assert iq.chunks_low_yield == [1]
    assert "chunks_low_yield" in iq.to_dict()
    assert "chunk_low_yield:1" in quality_to_warnings(iq)


def test_yield_ratio_property() -> None:
    s = ChunkStat(
        index=0, chars_in=1000, sentences_out=2, ok=True, kind="substantive", chars_out=200
    )
    assert abs(s.yield_ratio - 0.2) < 1e-9
    assert ChunkStat(index=0, chars_in=0, sentences_out=0, ok=True, kind="sparse").yield_ratio == 1.0
