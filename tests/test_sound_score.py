"""design/382 - the divisor, and the window that decides what goes into it.

The formula is simple enough to read off the page. The part that can be silently
wrong is the window: one that stops where the reference's last sound was emitted
cannot see a sound the reader added after it, which is the whole case the divisor
exists for. These pin the window down on a sheet built by hand, where the right
answer is known rather than measured.

A frame written `added(T)` is an extra sound the way a real one looks: the model is
fairly sure of it and the blank is its runner-up. That matters. The blank is what
CTC puts on anything it has no reference sound for, so the alignment leaves such a
frame alone instead of stretching a neighbouring sound over it, and a frame left
alone is a frame this can count.
"""
from __future__ import annotations

import math

import pytest

from sentence_reading.llm import hear_waveform as hw

PAD, A, B, C, T = 0, 1, 2, 3, 4
VOCAB = {PAD: "_", A: "a", B: "b", C: "c", T: "t"}


class Picked:
    """What `argmax` gives back: torch drops the axis it reduced."""

    def __init__(self, rows: list[int]):
        self.rows = rows

    def tolist(self) -> list[int]:
        return self.rows


class Sheet:
    """What the route hands in: column slicing, and a whole-vocabulary argmax."""

    def __init__(self, rows: list[list[float]]):
        self.rows = rows

    def __getitem__(self, key):
        _all, cols = key
        return Sheet([[row[c] for c in cols] for row in self.rows])

    def tolist(self) -> list[list[float]]:
        return self.rows

    def argmax(self, dim=-1) -> Picked:
        assert dim == -1
        return Picked([max(range(len(r)), key=r.__getitem__) for r in self.rows])


def added(tid: int) -> tuple[int]:
    """A sound the reference does not account for, with the blank behind it."""
    return (tid,)


def sheet_for(sequence: list) -> Sheet:
    """One frame per entry, almost all the probability on the sound named."""
    rows = []
    for want in sequence:
        if isinstance(want, tuple):
            share = {want[0]: 0.60, PAD: 0.35}
        else:
            share = {want: 0.96}
        rows.append([
            math.log(share.get(tid, 0.01)) for tid in sorted(VOCAB)
        ])
    return Sheet(rows)


@pytest.fixture(autouse=True)
def _vocab(monkeypatch):
    monkeypatch.setattr(hw, "_INV", dict(VOCAB))
    monkeypatch.setattr(hw, "_PAD", PAD)
    monkeypatch.setattr(hw, "_load_frames", lambda: None)


def test_the_fixture_says_what_it_looks_like():
    seq = [A, A, B, B, added(T), C, C]
    assert hw and sheet_for(seq).argmax(dim=-1).tolist() == [A, A, B, B, T, C, C]


def test_a_sound_added_after_the_reference_ran_out_is_counted():
    # The reader said `a b t` where the reference had `a b`, then `c`. The `t`
    # sits past the reference's last sound and inside the gap before `c`, which
    # is exactly the stretch a window ending at `b` cannot see.
    got = hw.sound_score_of(sheet_for([A, A, B, B, added(T), C, C]),
                            [["a", "b"], ["c"]])
    assert got is not None
    first, second = got
    assert first["n"] == 2.0
    assert first["said"] == 3.0, "the t has to land in the first word's window"
    # Three sounds said against two in the reference, so the divisor is three.
    assert first["sym"] == pytest.approx(first["sure"] * 2 / 3, abs=1e-6)
    assert first["sym"] < first["sure"]
    # And the word that did nothing wrong is not charged for it.
    assert second["said"] == 1.0
    assert second["sym"] == pytest.approx(second["sure"], abs=1e-6)


def test_a_clean_reading_is_not_charged_for_anything():
    got = hw.sound_score_of(sheet_for([A, A, B, B, C, C]),
                            [["a", "b"], ["c"]])
    assert got is not None
    for one in got:
        assert one["said"] == one["n"]
        assert one["sym"] == pytest.approx(one["sure"], abs=1e-6)
        assert one["sure"] > 0.9


def test_an_added_sound_the_blank_does_not_cover_still_costs():
    # When the blank is not the runner-up the alignment stretches a neighbouring
    # reference sound over the frame instead of leaving it. The sound is still
    # charged once -- that word's certainty falls, because its span now holds a
    # frame where its own sound was not said -- but it is charged to the
    # neighbour. Mis-attributed, never free.
    clean = hw.sound_score_of(sheet_for([A, A, B, B, C, C]),
                              [["a", "b"], ["c"]])
    messy = hw.sound_score_of(sheet_for([A, A, B, B, T, C, C]),
                              [["a", "b"], ["c"]])
    assert clean is not None and messy is not None
    assert sum(one["sym"] for one in messy) < sum(one["sym"] for one in clean)


def test_the_window_stops_when_the_next_word_has_no_reference():
    # The middle word is one the model knows no sound for. Widening past it would
    # charge the first word for that word's audio, which it did not say wrong.
    got = hw.sound_score_of(sheet_for([A, A, added(T), added(T), C, C]),
                            [["a"], ["zzz"], ["c"]])
    assert got is not None
    assert got[1] is None
    assert got[0]["said"] == 1.0, "the t belongs to the word with no reference"
    assert got[0]["sym"] == pytest.approx(got[0]["sure"], abs=1e-6)


def test_a_word_with_no_sound_the_model_knows_comes_back_empty():
    got = hw.sound_score_of(sheet_for([A, A, C, C]), [["a"], ["zzz"], ["c"]])
    assert got is not None
    assert got[1] is None
    assert got[0] is not None and got[2] is not None


def test_the_last_word_is_judged_to_the_end_of_the_recording():
    # Nothing follows the last word, so a sound added after it has nowhere else
    # to go. A window that stopped at the reference would let it through, and
    # `loss` read as `lost` is exactly this shape.
    got = hw.sound_score_of(sheet_for([A, A, C, C, added(T), added(T)]),
                            [["a"], ["c"]])
    assert got is not None
    assert got[1]["said"] == 2.0
    assert got[1]["sym"] == pytest.approx(got[1]["sure"] / 2, abs=1e-6)


def test_no_sheet_and_no_groups_are_refused_not_guessed():
    assert hw.sound_score_of(None, [["a"]]) is None
    assert hw.sound_score_of(sheet_for([A]), []) is None
    # Nothing the model knows: there is no lattice to align against.
    assert hw.sound_score_of(sheet_for([A, A]), [["zzz"]]) is None


def test_more_sounds_than_frames_is_refused():
    # The alignment cannot place six sounds on two frames, and a score invented
    # for it would be a number with nothing behind it.
    assert hw.sound_score_of(
        sheet_for([A, B]), [["a", "b", "c", "a", "b", "c"]]
    ) is None


def test_the_score_never_leaves_zero_to_one():
    runs = ([A, B, C], [A, A, A], [added(T)] * 3,
            [A, added(T), B, added(T), C, added(T)])
    for seq in runs:
        got = hw.sound_score_of(sheet_for(seq), [["a", "b"], ["c"]])
        if got is None:
            continue
        for one in got:
            if one is None:
                continue
            assert 0.0 <= one["sym"] <= 1.0
            assert one["sym"] <= one["sure"] + 1e-9
