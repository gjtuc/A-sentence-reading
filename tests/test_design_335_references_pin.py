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
    reference_signal_density,
    split_off_bibliography_lines,
)
from sentence_reading.llm.debone import _process_chunk_with_guard
from sentence_reading.llm.debone_quality import (
    ChunkStat,
    build_ingest_quality,
    pin_rescue_worth_keeping,
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


MDPI_SPLIT = (
    "Ostwald, W.R.; Nowak, P.A.; Jiang, Z.Q. Thermally stable single atom "
    "catalysts for the selective hydrogenation of alkynes over supported metals\n"
    "Catalysts 2023, 13, 1171. [CrossRef]\n"
    "Park, S.H.; Lee, J.K.; Chen, Y.M. Electrocatalytic hydrogen evolution on "
    "nickel phosphide surfaces studied by operando spectroscopy\n"
    "J. Membr. Sci. 2020, 12, 12345-12350. [CrossRef] [PubMed]\n"
)


def test_threshold_sits_in_the_measured_gap() -> None:
    """design/335 — 32 pinned chunks over 10 papers, and the gap has nothing in it.

    Highest true-body region 1.94, lowest true-reference region 6.11. The threshold
    must stay inside that gap, and not hug either edge.
    """
    from sentence_reading.llm.debone_quality import REF_SIGNAL_DENSITY_MAX as t

    assert 1.94 < t < 6.11
    assert t / 1.94 > 1.5  # headroom for a body region
    assert 6.11 / t > 1.5  # headroom for a reference region


def test_split_reference_entries_are_caught_by_density() -> None:
    """MDPI puts the author list in its own box: prose line by line, not prose.

    This is the cata13 leak — 62 ungrounded sentences shaped like
    `Catalysts 2023, 13, 117. [CrossRef]` and `Author, A.B.; Smith, C.D.`.
    """
    region = MDPI_SPLIT * 8
    assert reference_signal_density(region) > 5.0
    kept, _dropped = split_off_bibliography_lines(region)
    # The author-list lines look like prose, so the line filter alone keeps them.
    assert kept != ""
    # The region check is what refuses the rescue.
    assert pin_rescue_worth_keeping(kept, region) is False


def test_body_prose_density_is_near_zero() -> None:
    body = PROSE * 8
    assert reference_signal_density(body) == 0.0
    assert pin_rescue_worth_keeping(body, body) is True


def test_an_acknowledgements_name_list_does_not_refuse_the_rescue() -> None:
    """The `science.1212858` near miss: thanked names read as author initials.

    That region scored 1.94 under a 2.0 threshold — correct by 3%, for the wrong
    reason. It is prose, and the threshold now has room for it.
    """
    from sentence_reading.llm.debone_quality import REF_SIGNAL_DENSITY_MAX

    region = (
        PROSE
        + "\nAcknowledgements: we thank A. Becker, B. Cho, C. Muller, D. Rossi "
        "and E. Tanaka for helpful discussion and for sharing their samples.\n"
        + PROSE
    )
    assert reference_signal_density(region) < REF_SIGNAL_DENSITY_MAX
    assert pin_rescue_worth_keeping(region, region) is True


def test_years_in_body_prose_do_not_refuse_the_rescue() -> None:
    """A review paragraph cites years. Only reference-only signals count."""
    body = (
        PROSE
        + " Interest in this reaction has grown since 2015, and by 2019 several "
        "groups had reported comparable turnover numbers in 2020 and 2021."
    ) * 4
    assert reference_signal_density(body) == 0.0
    assert pin_rescue_worth_keeping(body, body) is True


def test_density_needs_several_hits() -> None:
    """One stray signal in a long survivor must not read as a reference list."""
    assert reference_signal_density("See doi:10.1021/x for details. " + PROSE) == 0.0


def test_mdpi_split_reference_chunk_is_dropped_end_to_end() -> None:
    chunk = _pin("references", MDPI_SPLIT * 8)
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=RuntimeError("must not call the model"),
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 11, 15, "", _Ctx())
    assert pairs == []
    assert stat.kind == "references"
    assert stat.references_pin_rejected is False


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
