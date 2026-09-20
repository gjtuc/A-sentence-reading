"""design/344 — measure lost *text*, not lost vocabulary.

`coverage_ratio` compares word **lists**. Measured on a real paper: deleting one
158-character sentence moved it by **0.12 points**, because every word in that
sentence also appeared somewhere else in the paper. So the instrument the whole
pipeline relies on to detect loss is blind to the scale of loss that matters, and
every "coverage 0.86, no regression" in this project's history was read off it.

Run against the ten-paper corpus, the text ruler found that **every paper** was
losing real sentences — 3 to 24 each — while the word-list ratio read 0.80 to 0.97.
"""

from __future__ import annotations

from sentence_reading.llm.debone_quality import (
    ChunkStat,
    build_ingest_quality,
    coverage_excluding_references,
    quality_to_warnings,
    text_coverage,
    text_fragments,
)
from sentence_reading.models import Sentence

PARAS = [
    "The conversion rose steadily once the reactor reached steady state, and the "
    "selectivity toward the liquid product followed the same trend.",
    "Carbon balances closed within three percent for all of the experiments reported "
    "in this section of the present work.",
    "The catalyst was dried at one hundred and twenty degrees for twelve hours before "
    "every single one of the reported runs.",
    "Peak fitting analysis was applied to gain information about the oxidation states "
    "of the supported metal particles.",
]
SOURCE = " ".join(PARAS)


def _sents(texts: list[str]) -> list[Sentence]:
    return [Sentence(id=f"s{i}", text=t, section="body") for i, t in enumerate(texts)]


# ------------------------------------------------------- the blindness, reproduced


def test_the_word_list_ruler_barely_moves_when_a_paragraph_goes() -> None:
    """The defect that motivated the chip, as a test rather than as a claim."""
    full = coverage_excluding_references(SOURCE, _sents(PARAS))
    minus = coverage_excluding_references(SOURCE, _sents(PARAS[:-1]))
    assert full - minus < 0.25, "a whole paragraph should barely move a word-list ratio"


def test_the_text_ruler_sees_it() -> None:
    full, missing_full = text_coverage(SOURCE, _sents(PARAS))
    minus, missing = text_coverage(SOURCE, _sents(PARAS[:-1]))
    assert full == 1.0
    assert missing_full == []
    assert minus < 0.85
    assert len(missing) == 1
    assert "oxidation states" in missing[0]


# ------------------------------------------------------- what counts as delivered


def test_light_editing_still_counts_as_delivered() -> None:
    """Deboning removes citation markers; that is not loss."""
    source = PARAS[0] + " [12,13]"
    ratio, missing = text_coverage(source, _sents([PARAS[0]]))
    assert ratio == 1.0
    assert missing == []


def test_a_fragment_split_across_two_sentences_still_counts() -> None:
    half = len(PARAS[0]) // 2
    ratio, missing = text_coverage(
        PARAS[0], _sents([PARAS[0][:half], PARAS[0][half:]])
    )
    assert ratio == 1.0
    assert missing == []


def test_nothing_delivered_reads_as_nothing() -> None:
    ratio, missing = text_coverage(SOURCE, [])
    assert ratio == 0.0
    assert len(missing) == len(PARAS)


def test_an_empty_source_is_not_a_failure() -> None:
    assert text_coverage("", _sents(PARAS)) == (1.0, [])


# ------------------------------------------------------- fragments worth reporting


def test_short_pieces_are_not_fragments() -> None:
    frags = text_fragments("Fig. 1. XRD. " + PARAS[0])
    assert all(len(f.split()) >= 6 for f in frags)


def test_apparatus_is_not_reported_as_missing() -> None:
    """The first run returned mastheads and page stamps, burying the real losses."""
    source = (
        "SCIENTIFIC REPORTS | 7:41797 | DOI: 10.1038/srep41797 www.nature.com/srep "
        "Downloaded on 5/28/2026 1:22:30 AM. "
        + PARAS[0]
    )
    _ratio, missing = text_coverage(source, _sents([PARAS[0]]))
    assert missing == []


def test_an_author_list_is_not_reported_as_missing() -> None:
    source = "Nelson,[b] Heeyeon Kim,[c] I. Sim,[c] Seong Ok Han,*[c] and John S. " + PARAS[0]
    _ratio, missing = text_coverage(source, _sents([PARAS[0]]))
    assert missing == []


def test_real_prose_is_reported() -> None:
    source = PARAS[0] + " " + PARAS[3]
    _ratio, missing = text_coverage(source, _sents([PARAS[0]]))
    assert len(missing) == 1
    assert "oxidation states" in missing[0]


# ------------------------------------------------------- reporting


def test_the_ruler_reaches_the_quality_record() -> None:
    iq = build_ingest_quality(
        raw_text=SOURCE,
        sentences=_sents(PARAS[:-1]),
        chunk_stats=[
            ChunkStat(index=0, chars_in=900, sentences_out=3, ok=True, kind="substantive")
        ],
        ungrounded_ids=[],
    )
    assert iq.text_missing_n == 1
    assert iq.text_coverage < 1.0
    d = iq.to_dict()
    assert d["text_missing_n"] == 1
    assert "text_coverage" in d
    w = quality_to_warnings(iq)
    assert "text_missing:1" in w


def test_a_clean_paper_says_nothing() -> None:
    iq = build_ingest_quality(
        raw_text=SOURCE,
        sentences=_sents(PARAS),
        chunk_stats=[
            ChunkStat(index=0, chars_in=900, sentences_out=4, ok=True, kind="substantive")
        ],
        ungrounded_ids=[],
    )
    assert iq.text_missing_n == 0
    assert iq.text_coverage == 1.0
    assert not [x for x in quality_to_warnings(iq) if x.startswith("text_")]


def test_the_ruler_never_breaks_the_ingest() -> None:
    """It measures the pipeline; it must not be able to stop it."""
    iq = build_ingest_quality(
        raw_text=None,  # type: ignore[arg-type]
        sentences=_sents(PARAS),
        chunk_stats=[],
        ungrounded_ids=[],
    )
    assert iq.text_coverage == 1.0
