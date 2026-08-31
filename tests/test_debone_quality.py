"""debone quality guards — chunk fallback, coverage, grounding, session persist (design/167)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm.debone import _process_chunk_with_guard
from sentence_reading.llm.debone_quality import (
    ChunkStat,
    IngestQuality,
    apply_grounding_flags,
    build_ingest_quality,
    check_sentence_grounded,
    chunk_kind,
    compute_coverage_ratio,
    fallback_split_chunk,
    quality_to_warnings,
)
from sentence_reading.models import PaperSession, Sentence


def test_chunk_kind_substantive() -> None:
    chunk = "Experimental methods and results " + ("word " * 40)
    assert chunk_kind(chunk) == "substantive"


def test_chunk_kind_references() -> None:
    chunk = (
        "References\n"
        "[1] A. Author, Journal 2020.\n"
        "[2] B. Author, Journal 2021.\n"
    )
    assert chunk_kind(chunk) == "references"


def test_fallback_split_chunk_produces_pairs() -> None:
    chunk = (
        "The catalytic activity was measured at elevated temperature. "
        "Results show improved performance over baseline materials."
    )
    pairs = fallback_split_chunk(chunk, object(), 2, 7)
    assert len(pairs) >= 1
    assert all(sec for _, sec in pairs)


def test_substantive_empty_uses_split_fallback() -> None:
    chunk = "Experimental section prose " + ("detail " * 30)

    class _Ctx:
        section_order = ["introduction", "experimental", "results"]

    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        return_value=[],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 2, 7, "", _Ctx())
    assert stat.fallback == "split"
    assert len(pairs) >= 1
    assert stat.ok is True


def test_references_empty_is_ok() -> None:
    chunk = (
        "References\n"
        + "\n".join(f"[{i}] Author et al., Journal {i}, 2020." for i in range(1, 12))
    )

    class _Ctx:
        section_order = ["references"]

    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        return_value=[],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 0, 1, "", _Ctx())
    assert stat.kind == "references"
    assert pairs == []
    assert stat.ok is True


def test_coverage_ratio_recall_biased() -> None:
    raw = "alpha beta gamma delta epsilon zeta"
    sentences = [
        Sentence(id="s1", text="alpha beta gamma", section="body"),
        Sentence(id="s2", text="missing tokens", section="body"),
    ]
    ratio = compute_coverage_ratio(raw, sentences)
    assert 0.45 < ratio < 1.0


def test_grounding_flags_ungrounded() -> None:
    raw = "Real experimental data from the catalyst study."
    sentences = [
        Sentence(
            id="s1",
            text="Earth crust minerals dominate global supply chains forever.",
            section="body",
        ),
    ]
    out, ids = apply_grounding_flags(sentences, raw)
    assert ids == ["s1"]
    assert "ungrounded" in out[0].quality_flags


def test_grounding_short_sentence_skipped() -> None:
    raw = "Some background context."
    sentences = [Sentence(id="s1", text="Short title.", section="title")]
    out, ids = apply_grounding_flags(sentences, raw)
    assert ids == []
    assert out[0].quality_flags == ()


def test_quality_to_warnings_codes() -> None:
    iq = IngestQuality(
        chunks_total=7,
        chunks_ok=5,
        chunks_failed=[3],
        chunks_fallback_split=[2, 6],
        coverage_ratio=0.58,
        body_sentence_count=40,
        body_ratio=0.35,
        ungrounded_count=2,
        ungrounded_ids=["s1", "s2"],
    )
    w = quality_to_warnings(iq)
    assert "chunk_fallback_split:2" in w
    assert "chunk_fallback_split:6" in w
    assert any(x.startswith("partial_debone:") for x in w)
    assert any(x.startswith("coverage_warn:") for x in w)
    assert any(x.startswith("high_body_ratio:") for x in w)
    assert "ungrounded_sentences:2" in w


def test_save_load_warnings_and_quality_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    session = PaperSession(
        title="Quality Persist Title Long Enough",
        sentences=[
            Sentence(
                id="s1",
                text="Measured activity at 800 C.",
                section="experimental",
                quality_flags=("ungrounded",),
            ),
        ],
        figures=[],
    )
    warnings = ["chunk_fallback_split:2", "coverage_warn:0.58"]
    ingest_quality = {"coverage_ratio": 0.58, "chunks_fallback_split": [2]}
    entry = pc.save_paper_session(
        session,
        debone=True,
        warnings=warnings,
        ingest_quality=ingest_quality,
    )
    assert entry is not None
    loaded, info = pc.load_cached_session(entry["id"])
    assert loaded is not None
    assert info["warnings"] == warnings
    assert info["ingest_quality"]["coverage_ratio"] == 0.58
    assert loaded.sentences[0].quality_flags == ("ungrounded",)
    meta = json.loads((tmp_path / entry["id"] / "session.json").read_text())
    assert meta["sentences"][0]["quality_flags"] == ["ungrounded"]
