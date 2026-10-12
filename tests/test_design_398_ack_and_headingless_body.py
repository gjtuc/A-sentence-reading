"""design/398 — Acknowledgements leave the reader; a headingless paper's Body is not a fault."""

from __future__ import annotations

import inspect

from sentence_reading.llm import debone, vision_ocr
from sentence_reading.llm.debone_quality import (
    ACK_DROP_MAX,
    drop_acknowledgement_sentences,
    quiet_headingless_body,
)
from sentence_reading.models import Sentence
from sentence_reading.pdf.body_headings import body_heading_n
from sentence_reading.pdf.section_flow import FlowBox


def _s(i: int, section: str) -> Sentence:
    return Sentence(id=f"s{i}", text=f"Sentence number {i}.", section=section)


def _paper(body_n: int, ack_n: int) -> list[Sentence]:
    return [_s(i, "Body") for i in range(body_n)] + [
        _s(body_n + i, "Acknowledgements") for i in range(ack_n)
    ]


def test_printed_heading_drops_the_acknowledgement() -> None:
    sents = _paper(40, 2)
    raw = "Body text.\n<<<ASR_SECTION acknowledgement>>>\nWe thank the funders."
    kept, dropped, kept_anyway = drop_acknowledgement_sentences(sents, raw)
    assert [s.id for s in dropped] == ["s40", "s41"]
    assert all(s.section == "Body" for s in kept) and len(kept) == 40
    assert kept_anyway == 0


def test_plain_heading_line_also_counts_as_printed() -> None:
    sents = _paper(40, 1)
    kept, dropped, _ = drop_acknowledgement_sentences(sents, "Body.\nAcknowledgements\nThanks.")
    assert len(dropped) == 1 and len(kept) == 40


def test_no_printed_heading_keeps_the_sentences() -> None:
    sents = _paper(40, 2)
    kept, dropped, kept_anyway = drop_acknowledgement_sentences(sents, "Body text only.")
    assert dropped == [] and len(kept) == 42 and kept_anyway == 2


def test_an_oversized_acknowledgement_is_kept() -> None:
    raw = "<<<ASR_SECTION acknowledgement>>>"
    big = _paper(400, ACK_DROP_MAX + 1)
    kept, dropped, kept_anyway = drop_acknowledgement_sentences(big, raw)
    assert dropped == [] and kept_anyway == ACK_DROP_MAX + 1
    share = _paper(20, 3)
    kept, dropped, kept_anyway = drop_acknowledgement_sentences(share, raw)
    assert dropped == [] and len(kept) == 23 and kept_anyway == 3


def test_headingless_paper_renames_the_body_warning() -> None:
    w = quiet_headingless_body(["body_headings:0", "high_body_ratio:0.97", "coverage_low"])
    assert w == ["body_headings:0", "body_ratio_headingless:0.97", "coverage_low"]
    assert not any(x.startswith("high_body_ratio") for x in w)


def test_paper_with_headings_keeps_the_body_warning() -> None:
    for w in (["body_headings:3", "high_body_ratio:0.40"], ["high_body_ratio:0.40"]):
        assert quiet_headingless_body(w) == w


def _heads(*texts: str, role: str = "sectionHeading") -> list[FlowBox]:
    return [FlowBox(1, 0, 0, 1, 1, t, role) for t in texts]


def test_communication_heads_count_zero_body_headings() -> None:
    boxes = _heads("Supporting Information", "Acknowledgements")
    boxes += _heads("We report a bimetallic catalyst for the reduction of oxygen.", role="")
    assert body_heading_n(boxes) == 0


def test_article_heads_count_their_body_headings() -> None:
    boxes = _heads(
        "ABSTRACT",
        "RESULTS AND DISCUSSION",
        "CONCLUSION",
        "METHODS",
        "REFERENCES AND NOTES",
        "ASSOCIATED CONTENT",
        "Conflict of Interest",
    )
    assert body_heading_n(boxes) == 3
    assert body_heading_n(_heads("2. Experimental", role="")) == 1


def test_debone_and_ocr_carry_the_new_signals() -> None:
    src = inspect.getsource(debone)
    assert "drop_acknowledgement_sentences(sentences, raw_text)" in src
    assert "sentences=[*sentences, *ack_dropped]" in src
    ocr = inspect.getsource(vision_ocr)
    assert "ordered_with_body_headings(pdf_path)" in ocr
    assert 'f"body_headings:{body_heads}"' in ocr
