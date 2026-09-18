"""design/335 — a `references` pin is not evidence that text is a reference list.

Azure's reference run started early on srep41797 and covered 23,090 of 45,968
characters. design/263 blanked every pinned chunk without looking, so roughly
12,000 characters of body prose were deleted with no warning anywhere: the chunks
were reported as substantive *failures*, which read as an LLM problem.
"""

from __future__ import annotations

from unittest.mock import patch

from sentence_reading.cite_refs import (
    is_bibliography_line,
    looks_like_prose_line,
    split_off_bibliography_lines,
)
from sentence_reading.llm.debone import _process_chunk_with_guard
from sentence_reading.llm.debone_quality import (
    ChunkStat,
    build_ingest_quality,
    quality_to_warnings,
)


class _Ctx:
    section_order = ["introduction", "methods", "results", "references"]


REF_LINES = [
    "1. Jiang, Z. et al. Surface chemistry of cobalt oxide. Nature 512, 22-28 (2014).",
    "2. Park, S. & Lee, J. Hydrogen evolution on nickel. J. Catal. 301, 10 (2013).",
    "[3] Chen, Y. Electrocatalysis review. Chem. Rev. 118, 2340 (2018).",
    "(4) Nowak, P. Doped perovskites. ACS Catal. 9, 100 (2019).",
]

PROSE = (
    "The conversion rose steadily once the reactor reached steady state, and the "
    "selectivity toward the liquid product followed the same trend across every "
    "run we performed with the supported catalyst. Carbon balances closed within "
    "three percent for all of the experiments reported in this section, which we "
    "take as evidence that the deactivation is not caused by coke deposition."
)


def _pin(section: str, body: str) -> str:
    return f"<<<ASR_SECTION {section}>>>\n{body}"


# ---------------------------------------------------------------- the predicate


def test_reference_entry_shapes_are_recognized() -> None:
    for line in REF_LINES:
        assert is_bibliography_line(line) is True, line


def test_prose_is_not_a_reference_line() -> None:
    assert is_bibliography_line(PROSE) is False
    for line in PROSE.split(". "):
        assert is_bibliography_line(line) is False


def test_numbered_procedure_step_is_not_a_reference() -> None:
    """A methods list must survive; only a citation signal makes it a reference."""
    assert is_bibliography_line("2. Add the acid slowly while stirring.") is False
    assert is_bibliography_line("3. Dry the powder overnight in a vacuum oven.") is False


def test_long_numbered_paragraph_is_not_a_reference() -> None:
    assert is_bibliography_line("1. " + PROSE * 2) is False


def test_split_keeps_prose_and_drops_entries() -> None:
    text = PROSE + "\n" + "\n".join(REF_LINES)
    kept, dropped = split_off_bibliography_lines(text)
    assert kept == PROSE
    assert dropped > 0
    for line in REF_LINES:
        assert line not in kept


def test_split_of_a_pure_reference_list_keeps_nothing() -> None:
    kept, dropped = split_off_bibliography_lines("\n".join(REF_LINES * 5))
    assert kept == ""
    assert dropped > 0


# ---------------------------------------------------------------- deletion gate


def test_genuine_reference_chunk_is_still_dropped() -> None:
    """design/263 must not regress: a real bibliography never becomes practice."""
    chunk = _pin("references", "References\n" + "\n".join(REF_LINES * 6))
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=RuntimeError("must not call the model"),
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 9, 12, "", _Ctx())
    assert pairs == []
    assert stat.kind == "references"
    assert stat.ok is True
    assert stat.references_pin_rejected is False
    assert stat.bib_chars_dropped > 0


def test_prose_swallowed_by_the_pin_survives() -> None:
    chunk = _pin("references", PROSE)
    out = [(s + ".", "references") for s in PROSE.split(". ")]
    with patch("sentence_reading.llm.debone._process_one_chunk", return_value=out):
        pairs, stat = _process_chunk_with_guard(chunk, 7, 12, "", _Ctx())
    assert stat.references_pin_rejected is True
    assert stat.kind == "substantive"
    assert len(pairs) == len(out)
    # Rescued prose is body, not a reference entry.
    assert {sec for _t, sec in pairs} == {"body"}


def test_mixed_chunk_keeps_the_prose_half() -> None:
    """The run boundary lands mid-chunk; keep what is not a reference entry."""
    chunk = _pin("references", PROSE + "\n" + "\n".join(REF_LINES * 3))
    seen: dict[str, str] = {}

    def _fake(work: str, *_a: object, **_k: object) -> list[tuple[str, str]]:
        seen["work"] = work
        return [(PROSE, "references")]

    with patch("sentence_reading.llm.debone._process_one_chunk", side_effect=_fake):
        pairs, stat = _process_chunk_with_guard(chunk, 8, 12, "", _Ctx())
    assert stat.references_pin_rejected is True
    assert stat.bib_chars_dropped > 0
    assert PROSE in seen["work"]
    for line in REF_LINES:
        assert line not in seen["work"]
    assert pairs and pairs[0][1] == "body"


def test_rescued_chunk_is_not_reported_as_a_failure() -> None:
    """The old symptom: a deliberate drop showed up as `partial_debone`."""
    chunk = _pin("references", "References\n" + "\n".join(REF_LINES * 6))
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=RuntimeError("must not call the model"),
    ):
        _pairs, stat = _process_chunk_with_guard(chunk, 9, 12, "", _Ctx())
    iq = build_ingest_quality(
        raw_text=PROSE,
        sentences=[],
        chunk_stats=[stat],
        ungrounded_ids=[],
    )
    assert iq.chunks_failed == []
    assert iq.chunks_ok == 1


def test_mostly_references_chunk_is_not_rescued_by_stray_lines() -> None:
    """The srep chunk 10 case: 89% reference entries plus a few stray lines.

    Rescuing on the strays alone would push reference fragments into practice.
    """
    strays = "Additional Information\nCompeting financial interests statement here."
    chunk = _pin("references", "\n".join(REF_LINES * 7) + "\n" + strays)
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=RuntimeError("must not call the model"),
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 10, 12, "", _Ctx())
    assert pairs == []
    assert stat.kind == "references"
    assert stat.references_pin_rejected is False


def test_rescue_share_threshold() -> None:
    from sentence_reading.llm.debone_quality import pin_rescue_worth_keeping

    refs = "\n".join(REF_LINES * 7)
    assert pin_rescue_worth_keeping(PROSE, PROSE) is True
    # srep chunks 7-8: paragraph-length prose lines dominate the chunk.
    assert pin_rescue_worth_keeping(PROSE * 2, PROSE * 2 + "\n" + refs) is True
    assert pin_rescue_worth_keeping("Additional Information", refs) is False
    assert pin_rescue_worth_keeping("", refs) is False


def test_wrapped_reference_tail_does_not_survive() -> None:
    """The leak that matters: line two of a reference entry is not a sentence."""
    tails = [
        "Nature 512, 22-28 (2014).",
        "J. Am. Chem. Soc. 140, 1201-1210, doi:10.1021/jacs.7b00001 (2018).",
        "Angew. Chem. Int. Ed. 57, 1120 (2018). 12, 44 (2011). 8, 90 (2009).",
    ]
    for line in tails:
        assert looks_like_prose_line(line) is False, line
    kept, dropped = split_off_bibliography_lines("\n".join(tails))
    assert kept == ""
    assert dropped > 0


def test_heading_and_footer_lines_do_not_survive() -> None:
    for line in ("References", "Additional Information", "SCIENTIFIC REPORTS | 7:41797"):
        assert looks_like_prose_line(line) is False, line


def test_real_prose_line_is_prose() -> None:
    assert looks_like_prose_line(PROSE) is True
    assert looks_like_prose_line(
        "The catalyst retained its activity for more than forty hours on stream."
    ) is True


def test_other_pins_are_untouched() -> None:
    chunk = _pin("methods", PROSE)
    out = [(PROSE, "results")]
    with patch("sentence_reading.llm.debone._process_one_chunk", return_value=out):
        pairs, stat = _process_chunk_with_guard(chunk, 5, 12, "", _Ctx())
    assert stat.bib_chars_dropped == 0
    assert stat.references_pin_rejected is False
    assert pairs == [(PROSE, "methods")]


# ---------------------------------------------------------------- reporting


def test_pin_rejection_and_dropped_chars_are_reported() -> None:
    stats = [
        ChunkStat(
            index=7,
            chars_in=5000,
            sentences_out=20,
            ok=True,
            kind="substantive",
            references_pin_rejected=True,
            bib_chars_dropped=120,
        ),
        ChunkStat(
            index=10,
            chars_in=5000,
            sentences_out=0,
            ok=True,
            kind="references",
            bib_chars_dropped=4800,
        ),
    ]
    iq = build_ingest_quality(
        raw_text=PROSE, sentences=[], chunk_stats=stats, ungrounded_ids=[]
    )
    assert iq.references_pin_rejected == [7]
    assert iq.bib_chars_dropped == 4920
    d = iq.to_dict()
    assert d["bib_chars_dropped"] == 4920
    assert d["references_pin_rejected"] == [7]
    assert "references_pin_rejected:7" in quality_to_warnings(iq)
