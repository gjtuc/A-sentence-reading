"""design/351 — the order was fine; the measure was reading a different book.

Five of ten papers reported 40% or more of their sentences out of source order, while
three reported under 10%. A ten-fold split that clean is a cause you can find, and there
were two.

**The wrong text.** `source_order_stats` was called with `text_pre_filter`, the raw page
text. The sentences come from the reading-order text, so on a two-column paper every
place the two orders differ registered as a backward step. Re-anchored in the text the
sentences were actually made from, `d4cs` goes from 44.5% to **0.9%**.

**The wrong rule.** Counting a step below the running *maximum* turns one displaced
sentence into a verdict on everything after it — `advmat` read 24.8% that way while only
1.8% of its sentences stepped back from the one before. Counting only a step from the
previous sentence has the opposite blind spot: move a whole block and a single pair is
out of place, which is the very defect design/322 exists to catch.

The length of the longest run already in order answers both. One displaced sentence costs
one; a swapped half costs half.

Measured over eleven runs of ten papers, anchored correctly: **0.0% to 6.1%**.
"""

from __future__ import annotations

from sentence_reading.llm.debone_quality import (
    ORDER_BACKWARD_PCT_WARN,
    order_warnings,
    source_order_stats,
)
from sentence_reading.models import Sentence

ROWS = [" ".join("word%d_%d" % (i, j) for j in range(6)) for i in range(24)]
SRC = " ".join(ROWS)


def _sents(rows: list[str]) -> list[Sentence]:
    return [Sentence(id=str(i), text=t, section="body") for i, t in enumerate(rows)]


# ------------------------------------------------- the rule


def test_the_papers_own_order_is_clean() -> None:
    stats = source_order_stats(SRC, _sents(ROWS))
    assert stats["anchored_n"] == 24
    assert stats["backward_n"] == 0
    assert order_warnings(stats) == []


def test_a_swapped_half_is_still_caught() -> None:
    """What design/322 was built for. The previous-sentence rule would see one pair."""
    stats = source_order_stats(SRC, _sents(ROWS[12:] + ROWS[:12]))
    assert stats["backward_pct"] == 50.0
    assert order_warnings(stats) == ["sentence_order_backward:50.0"]


def test_one_displaced_sentence_is_not_a_scrambled_paper() -> None:
    """What the running-maximum rule got wrong: it blamed every sentence after it."""
    moved = ROWS[:5] + [ROWS[23]] + ROWS[5:23]
    stats = source_order_stats(SRC, _sents(moved))
    assert stats["backward_n"] == 1
    assert stats["backward_pct"] < ORDER_BACKWARD_PCT_WARN
    assert order_warnings(stats) == []


def test_two_displaced_sentences_cost_two() -> None:
    moved = [ROWS[20]] + ROWS[:10] + [ROWS[22]] + ROWS[10:20] + ROWS[21:22] + ROWS[23:]
    stats = source_order_stats(SRC, _sents(moved))
    assert stats["backward_n"] <= 3


def test_a_fully_reversed_paper_is_almost_all_out_of_order() -> None:
    stats = source_order_stats(SRC, _sents(list(reversed(ROWS))))
    assert stats["backward_pct"] > 90.0


# ------------------------------------------------- the text


def test_anchoring_in_a_differently_ordered_text_is_what_went_wrong() -> None:
    """The sentences are in their own order; the *other* text is what disagrees. This is
    the shape of a two-column page read down one column and then the other."""
    interleaved = " ".join(ROWS[0::2] + ROWS[1::2])
    in_own_text = source_order_stats(SRC, _sents(ROWS))
    in_other_text = source_order_stats(interleaved, _sents(ROWS))
    assert in_own_text["backward_n"] == 0
    assert in_other_text["backward_n"] > 5


def test_the_threshold_sits_between_measured_papers_and_a_swap() -> None:
    assert 6.1 < ORDER_BACKWARD_PCT_WARN < 50.0


# ------------------------------------------------- unchanged guarantees


def test_unanchored_sentences_are_still_excluded() -> None:
    stats = source_order_stats(SRC, _sents(ROWS[:3]) + _sents(["nothing like the source"]))
    assert stats["anchored_n"] == 3


def test_too_few_anchors_says_nothing() -> None:
    assert order_warnings({"anchored_n": 19, "backward_pct": 80.0}) == []
