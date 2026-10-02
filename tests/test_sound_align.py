"""design/381 - the hand-written CTC alignment has to agree with the real one.

The whole certainty score rests on knowing which stretch of the take each reference
sound landed on. That is `torchaudio.functional.forced_align`, which is not in the
server image, so `sound_align.align` writes the Viterbi pass out by hand. If the two
disagree the score is built on sand, so this compares them token for token wherever
torchaudio is installed, and checks the shape of the answer where it is not.
"""
from __future__ import annotations

import math
import random

import pytest

from sentence_reading.llm.sound_align import align, certainty_by_group

BLANK = 0


def log_softmax(rows: list[list[float]]) -> list[list[float]]:
    out = []
    for row in rows:
        top = max(row)
        denom = math.log(sum(math.exp(v - top) for v in row)) + top
        out.append([v - denom for v in row])
    return out


def sheet(frames: int, vocab: int, seed: int) -> list[list[float]]:
    rng = random.Random(seed)
    return log_softmax(
        [[rng.uniform(-4.0, 4.0) for _ in range(vocab)] for _ in range(frames)]
    )


def test_refuses_what_cannot_fit():
    assert align(sheet(2, 5, 1), [1, 2, 3, 4], blank=BLANK) is None
    assert align(sheet(10, 5, 1), [], blank=BLANK) is None
    assert align([], [1], blank=BLANK) is None


def test_a_repeated_token_needs_a_blank_between():
    # Two frames cannot hold `1 blank 1`.
    assert align(sheet(2, 5, 2), [1, 1], blank=BLANK) is None
    assert align(sheet(3, 5, 2), [1, 1], blank=BLANK) is not None


def test_spans_are_in_order_and_do_not_overlap():
    spans = align(sheet(40, 8, 3), [1, 2, 3, 1, 4], blank=BLANK)
    assert spans is not None
    assert len(spans) == 5
    last = -1
    for lo, hi, sure in spans:
        assert lo < hi
        assert lo >= last
        last = hi - 1
        assert 0.0 <= sure <= 1.0


def test_a_clear_sheet_gives_near_certainty():
    # Frames 0-4 scream token 1, frames 5-9 scream token 2.
    rows = []
    for t in range(10):
        row = [-9.0] * 4
        row[1 if t < 5 else 2] = 9.0
        rows.append(row)
    spans = align(log_softmax(rows), [1, 2], blank=BLANK)
    assert spans is not None
    assert spans[0][2] > 0.99
    assert spans[1][2] > 0.99
    assert spans[0][1] <= spans[1][0]


def test_certainty_by_group_keeps_every_sound():
    got = certainty_by_group(sheet(40, 8, 4), [[1, 2], [3], [4, 5, 6]], blank=BLANK)
    assert got is not None
    assert [len(g) for g in got] == [2, 1, 3]
    assert all(0.0 <= v <= 1.0 for g in got for v in g)


def test_a_group_the_model_cannot_be_asked_about_is_empty():
    got = certainty_by_group(sheet(40, 8, 5), [[1, 2], [], [3]], blank=BLANK)
    assert got is not None
    assert got[1] == []
    assert len(got[0]) == 2 and len(got[2]) == 1


def test_agrees_with_torchaudio():
    """The one that matters. Same lattice, same answer."""
    torch = pytest.importorskip("torch")
    fa = pytest.importorskip("torchaudio.functional")

    for seed in range(1, 12):
        rows = sheet(60, 10, seed)
        tokens = [1, 2, 3, 2, 4, 5, 1, 6]
        mine = align(rows, tokens, blank=BLANK)
        assert mine is not None

        probs = torch.tensor(rows).unsqueeze(0)
        targets = torch.tensor([tokens], dtype=torch.int32)
        aligned, score = fa.forced_align(probs, targets, blank=BLANK)
        theirs = fa.merge_tokens(aligned[0], score[0].exp(), blank=BLANK)

        assert len(theirs) == len(mine), f"seed {seed}"
        for i, span in enumerate(theirs):
            lo, hi, sure = mine[i]
            assert int(span.token) == tokens[i], f"seed {seed} token {i}"
            assert int(span.start) == lo, f"seed {seed} start {i}"
            assert int(span.end) == hi, f"seed {seed} end {i}"
            assert abs(float(span.score) - sure) < 1e-5, f"seed {seed} score {i}"
