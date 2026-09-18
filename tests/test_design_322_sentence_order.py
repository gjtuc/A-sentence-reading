"""design/322 — stored sentence order is the paper's order.

Only one sentence is on screen, so a reordering is invisible to the reader.
No paper text here: short ASCII strings only.
"""

from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.debone import _assemble_sentences
from sentence_reading.llm.debone_quality import (
    order_warnings,
    source_order_stats,
)
from sentence_reading.models import Sentence

ROOT = Path(__file__).resolve().parents[1]


def _order(pairs: list[tuple[str, str]]) -> list[str]:
    return [s.text for s in _assemble_sentences(pairs)]


def _sections(pairs: list[tuple[str, str]]) -> list[str]:
    return [s.section for s in _assemble_sentences(pairs)]


def test_methods_after_discussion_keeps_the_paper_order():
    # A journal that prints Methods at the end. The old rank table showed
    # Methods before Results.
    pairs = [
        ("t", "title"),
        ("a", "abstract"),
        ("i", "introduction"),
        ("r1", "results"),
        ("r2", "results"),
        ("d", "discussion"),
        ("m1", "methods"),
        ("m2", "methods"),
        ("c", "conclusion"),
    ]
    assert _order(pairs) == ["t", "a", "i", "r1", "r2", "d", "m1", "m2", "c"]


def test_methods_and_experimental_no_longer_interleave():
    # Both used to share rank 3, so a stable secondary sort alternated them.
    pairs = [
        ("m1", "methods"),
        ("m2", "methods"),
        ("e1", "experimental"),
        ("e2", "experimental"),
        ("m3", "methods"),
    ]
    assert _order(pairs) == ["m1", "m2", "e1", "e2", "m3"]
    assert _sections(pairs) == [
        "methods",
        "methods",
        "experimental",
        "experimental",
        "methods",
    ]


def test_body_label_no_longer_jumps_past_the_conclusion():
    # `body` ranked 7, after conclusion at 6, so an unrecognised numbered
    # heading relocated its whole section to the tail.
    pairs = [
        ("i", "introduction"),
        ("b1", "body"),
        ("b2", "body"),
        ("c", "conclusion"),
    ]
    assert _order(pairs) == ["i", "b1", "b2", "c"]


def test_title_card_still_leads():
    pairs = [
        ("a", "abstract"),
        ("t", "title"),
        ("i", "introduction"),
    ]
    assert _order(pairs) == ["t", "a", "i"]


def test_only_the_first_title_card_survives():
    pairs = [
        ("t1", "title"),
        ("a", "abstract"),
        ("t2", "title"),
    ]
    assert _order(pairs) == ["t1", "a"]


def test_source_order_is_kept_inside_one_section():
    pairs = [(f"s{i}", "results") for i in range(12)]
    assert _order(pairs) == [f"s{i}" for i in range(12)]


def test_ids_are_renumbered_in_stored_order():
    pairs = [("x", "results"), ("y", "introduction"), ("z", "title")]
    out = _assemble_sentences(pairs)
    assert [s.id for s in out] == ["sent_000000", "sent_000001", "sent_000002"]
    assert [s.text for s in out] == ["z", "x", "y"]


def test_rank_table_is_gone():
    src = (ROOT / "src/sentence_reading/llm/debone.py").read_text(encoding="utf-8")
    assert "_SECTION_ORDER" not in src


def _sent(text: str) -> Sentence:
    return Sentence(id="x", text=text, section="results")


def test_order_stats_are_clean_when_stored_order_follows_the_source():
    src = " ".join(f"alpha{i} beta{i} gamma{i} delta{i} epsilon{i} zeta{i}" for i in range(12))
    sents = [
        _sent(f"alpha{i} beta{i} gamma{i} delta{i} epsilon{i} zeta{i}")
        for i in range(12)
    ]
    stats = source_order_stats(src, sents)
    assert stats["anchored_n"] == 12
    assert stats["backward_n"] == 0
    assert stats["backward_pct"] == 0.0


def test_order_stats_count_backward_steps_when_blocks_are_swapped():
    src = " ".join(f"alpha{i} beta{i} gamma{i} delta{i} epsilon{i} zeta{i}" for i in range(12))
    rows = [
        f"alpha{i} beta{i} gamma{i} delta{i} epsilon{i} zeta{i}" for i in range(12)
    ]
    # Second half stored first — the section-rank reordering shape.
    swapped = [_sent(t) for t in rows[6:] + rows[:6]]
    stats = source_order_stats(src, swapped)
    assert stats["anchored_n"] == 12
    assert stats["backward_n"] >= 6


def test_order_warnings_stay_quiet_on_a_short_or_clean_paper():
    # Under 20 anchored sentences the ratio is not trustworthy.
    assert order_warnings({"anchored_n": 8, "backward_pct": 90.0}) == []
    assert order_warnings({"anchored_n": 200, "backward_pct": 3.0}) == []


def test_order_warnings_name_a_scrambled_paper():
    w = order_warnings({"anchored_n": 219, "backward_pct": 61.19})
    assert w == ["sentence_order_backward:61.2"]


def test_unanchored_sentences_are_excluded_not_guessed():
    src = "alpha beta gamma delta epsilon zeta eta theta"
    sents = [_sent("alpha beta gamma delta epsilon zeta"), _sent("nowhere near this text at all")]
    stats = source_order_stats(src, sents)
    assert stats["anchored_n"] == 1


def test_order_gate_script_exists_and_prints_no_paper_text():
    gate = ROOT / "scripts/sentence_order_gate.py"
    assert gate.is_file()
    src = gate.read_text(encoding="utf-8")
    # ASCII-only JSON, counts and offsets. design/301 console rule.
    assert "ensure_ascii=True" in src
    assert "section_order_inversions" in src
    assert "backward_steps" in src
