"""design/336 — a heuristic may only delete what it can name, and must say so.

design/335 made the section *pin* prove its case before deleting. Two audits of the
same bug class found the duty was not applied evenly:

- `chunk_kind` deletes a whole chunk on its own `references` verdict, with
  `ok=True`, `bib_chars_dropped=0` and no warning. `REFERENCES_HEAD_RE` also
  matches `Acknowledgements`, and the `extract_bibliography(chunk) >= 2`
  short-circuit runs before the prose check, so one chunk holding
  acknowledgements, references and an appendix lost the appendix silently.
- `bib_chars_dropped` reached `to_dict()` and stopped: no warning at any size.
- The implausible-cut refusal lived in `practice_text_for_coverage`, which had no
  callers. The live denominator `practice_text_only` ran unguarded.
- `slot_census` reports `unused_body_n` after the repair that zeroes it, so both
  design/321 verdicts are dead. All ten audited papers report 0.
- `section_flow` deletes boxes at six gates and counted none of them.
"""

from __future__ import annotations

from unittest.mock import patch

from sentence_reading.llm.debone import _process_chunk_with_guard
from sentence_reading.llm.debone_quality import (
    BIB_DROPPED_REPORT_CHARS,
    ChunkStat,
    build_ingest_quality,
    chunk_kind,
    practice_text_for_coverage,
    practice_text_only,
    quality_to_warnings,
)


class _Ctx:
    section_order = ["introduction", "methods", "results", "references"]


REF_LINES = [
    "1. Jiang, Z. et al. Surface chemistry of cobalt oxide. Nature 512, 22 (2014).",
    "2. Park, S. & Lee, J. Hydrogen evolution on nickel. J. Catal. 301, 10 (2013).",
    "3. Chen, Y. Electrocatalysis review. Chem. Rev. 118, 2340 (2018).",
]

APPENDIX = (
    "Appendix A. The reactor was operated at atmospheric pressure throughout, and "
    "the gas hourly space velocity was held constant while the temperature ramped. "
    "Carbon balances closed within three percent across every run reported here, "
    "which we take as evidence that no coke accumulated on the support during the "
    "measurement window described in the preceding section of this work."
)


# ------------------------------------------------- chunk_kind's own verdict


def test_a_references_heading_in_the_head_condemns_the_whole_chunk() -> None:
    """The precondition, measured rather than assumed.

    `chunk_kind` searches only `chunk[:800]`, and the
    `extract_bibliography(chunk) >= 2` short-circuit returns before the prose check
    ever runs. So prose *ahead of* the heading is condemned too.
    """
    assert chunk_kind("References\n" + "\n".join(REF_LINES * 2) + "\n" + APPENDIX * 3) == (
        "references"
    )
    # Prose ahead of the heading is condemned too, as long as the heading still
    # lands inside the 800-character window the check looks at.
    assert chunk_kind(APPENDIX + "\nReferences\n" + "\n".join(REF_LINES * 3)) == (
        "references"
    )
    # An `Acknowledgements` heading alone does not trip it: the prose-line check
    # catches that case, so the audit's example was not the live hazard.
    assert chunk_kind("Acknowledgements\nWe thank the staff.\n" + APPENDIX * 3) != (
        "references"
    )


def test_prose_ahead_of_a_references_heading_survives() -> None:
    chunk = APPENDIX + "\nReferences\n" + "\n".join(REF_LINES * 3)
    assert chunk_kind(chunk) == "references"
    seen: dict[str, str] = {}

    def _fake(work: str, *_a: object, **_k: object) -> list[tuple[str, str]]:
        seen["work"] = work
        return [(work, "body")]

    with patch("sentence_reading.llm.debone._process_one_chunk", side_effect=_fake):
        pairs, stat = _process_chunk_with_guard(chunk, 4, 9, "", _Ctx())
    assert stat.references_verdict == "kind"
    assert stat.references_pin_rejected is True
    assert stat.kind == "substantive"
    assert pairs and APPENDIX[:50] in pairs[0][0]
    assert APPENDIX[:50] in seen["work"]
    for line in REF_LINES:
        assert line not in seen["work"]


def test_prose_after_a_references_heading_survives() -> None:
    chunk = "References\n" + "\n".join(REF_LINES * 2) + "\n" + APPENDIX * 3
    assert chunk_kind(chunk) == "references"
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=lambda work, *a, **k: [(work, "body")],
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 4, 9, "", _Ctx())
    assert stat.references_pin_rejected is True
    assert pairs and APPENDIX[:50] in pairs[0][0]
    assert stat.bib_chars_dropped > 0


def test_a_real_reference_chunk_is_still_deleted_without_calling_the_model() -> None:
    chunk = "References\n" + "\n".join(REF_LINES * 8)
    with patch(
        "sentence_reading.llm.debone._process_one_chunk",
        side_effect=RuntimeError("must not call the model"),
    ):
        pairs, stat = _process_chunk_with_guard(chunk, 8, 9, "", _Ctx())
    assert pairs == []
    assert stat.kind == "references"
    assert stat.ok is True
    assert stat.references_verdict == "kind"
    assert stat.references_pin_rejected is False
    # The whole point: the deletion is now accounted for.
    assert stat.bib_chars_dropped > 0


def test_the_two_routes_are_reported_apart() -> None:
    stats = [
        ChunkStat(
            index=3,
            chars_in=5000,
            sentences_out=9,
            ok=True,
            kind="substantive",
            references_pin_rejected=True,
            references_verdict="pin",
        ),
        ChunkStat(
            index=4,
            chars_in=5000,
            sentences_out=9,
            ok=True,
            kind="substantive",
            references_pin_rejected=True,
            references_verdict="kind",
        ),
    ]
    iq = build_ingest_quality(
        raw_text=APPENDIX, sentences=[], chunk_stats=stats, ungrounded_ids=[]
    )
    assert iq.references_pin_rejected == [3]
    assert iq.references_kind_rejected == [4]
    w = quality_to_warnings(iq)
    assert "references_pin_rejected:3" in w
    assert "references_kind_rejected:4" in w


# ------------------------------------------------- the write-only counter


def test_bib_chars_dropped_becomes_a_warning() -> None:
    stats = [
        ChunkStat(
            index=0,
            chars_in=5000,
            sentences_out=0,
            ok=True,
            kind="references",
            bib_chars_dropped=4800,
        )
    ]
    iq = build_ingest_quality(
        raw_text=APPENDIX, sentences=[], chunk_stats=stats, ungrounded_ids=[]
    )
    assert "bib_chars_dropped:4800" in quality_to_warnings(iq)


def test_a_trivial_bibliography_drop_is_not_noise() -> None:
    stats = [
        ChunkStat(
            index=0,
            chars_in=900,
            sentences_out=5,
            ok=True,
            kind="substantive",
            bib_chars_dropped=BIB_DROPPED_REPORT_CHARS - 1,
        )
    ]
    iq = build_ingest_quality(
        raw_text=APPENDIX, sentences=[], chunk_stats=stats, ungrounded_ids=[]
    )
    assert not any(x.startswith("bib_chars_dropped") for x in quality_to_warnings(iq))


# ------------------------------------------------- the dead denominator guard


def test_the_live_denominator_refuses_an_implausible_cut() -> None:
    """An early `References` mention must not cut the paper away."""
    body = APPENDIX * 12
    text = "References therein describe the method.\n" + body
    kept = practice_text_only(text)
    # Most of the paper has to survive, whatever the cut proposed.
    assert len(kept) > len(text) * 0.25
    assert APPENDIX[:60] in kept


def test_both_denominator_names_are_one_definition() -> None:
    text = APPENDIX * 4 + "\nReferences\n" + "\n".join(REF_LINES * 6)
    assert practice_text_for_coverage(text) == practice_text_only(text)


def test_a_plausible_bibliography_cut_still_happens() -> None:
    body = APPENDIX * 4
    text = body + "\nReferences\n" + "\n".join(REF_LINES * 6)
    kept = practice_text_only(text)
    assert len(kept) < len(text)
    assert REF_LINES[0] not in kept
