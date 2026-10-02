"""design/381 - the hear route's certainty row, and what it does when it cannot.

The route reports; it does not yet score. So the thing to pin down is that it never
takes a take down with it: no reference, no sheet, a sheet it cannot align, or a
model that throws must all leave the sounds intact and say which it was.
"""
from __future__ import annotations

import math

from sentence_reading.api.app import _slot_certainty
from sentence_reading.llm.evidence_bus import _safe_details


def log_softmax(rows):
    out = []
    for row in rows:
        top = max(row)
        denom = math.log(sum(math.exp(v - top) for v in row)) + top
        out.append([v - denom for v in row])
    return out


class FakeSheet:
    """Stands in for the torch tensor: the route only ever slices columns."""

    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, key):
        _all, cols = key
        return FakeSheet([[row[c] for c in cols] for row in self.rows])

    def tolist(self):
        return self.rows


ROWS = ("slot_sym", "slot_sure", "slot_floor", "slot_said")


def test_no_reference_says_so():
    for text in ("", "  |  "):
        got = _slot_certainty(None, text)
        assert got["sure_code"] == "no_target"
        assert all(got[key] == "" for key in ROWS)


def test_a_reference_without_a_sheet_says_so():
    got = _slot_certainty(None, "a b c")
    assert got["sure_code"] == "no_sheet"
    assert all(got[key] == "" for key in ROWS)


def test_a_sheet_that_throws_does_not_take_the_take_down():
    class Boom:
        def __getitem__(self, key):
            raise RuntimeError("no")

    got = _slot_certainty(Boom(), "a b c")
    assert got["sure_code"] != "ok"
    assert all(got[key] == "" for key in ROWS)


def test_the_rows_are_digits_and_dashes_only(monkeypatch):
    # Two words, the second one unaskable.
    monkeypatch.setattr(
        "sentence_reading.llm.hear_waveform.sound_score_of",
        lambda sheet, groups: [
            {"sure": 0.85, "low": 0.80, "n": 2.0, "said": 4.0, "sym": 0.425},
            None,
        ],
    )
    got = _slot_certainty(FakeSheet([[0.0]]), "x y | z")
    assert got["sure_code"] == "ok"
    assert got["slot_sym"] == "42 -"
    assert got["slot_sure"] == "85 -"
    assert got["slot_floor"] == "8000 -"
    assert got["slot_said"] == "4 -"
    for key in ROWS:
        assert set(got[key]) <= set("0123456789 -")


def test_the_rows_survive_sanitising():
    out = _safe_details({"slot_sym": "42 90 -", "slot_sure": "85 90 -",
                         "slot_floor": "8000 12 -", "slot_said": "4 3 -"})
    assert out["slot_sym"] == "42 90 -"
    assert out["slot_sure"] == "85 90 -"
    assert out["slot_floor"] == "8000 12 -"
    assert out["slot_said"] == "4 3 -"


def test_a_real_sheet_lines_up_with_the_words_sent(monkeypatch):
    """One group per `|`, in order, even when the model knows none of a group."""
    seen: list[list[list[str]]] = []

    def fake(sheet, groups):
        seen.append(groups)
        return [{"sure": 1.0, "low": 1.0, "n": 1.0, "said": 1.0, "sym": 1.0}
                for _ in groups]

    monkeypatch.setattr(
        "sentence_reading.llm.hear_waveform.sound_score_of", fake
    )
    got = _slot_certainty(FakeSheet([[0.0]]), "a b | c | d e f")
    assert got["sure_code"] == "ok"
    assert seen == [[["a", "b"], ["c"], ["d", "e", "f"]]]
    assert got["slot_sym"] == "100 100 100"
    assert got["slot_floor"] == "10000 10000 10000"


def _rows_from(monkeypatch, got, asked="a b c | d | e f"):
    """design/384 - the row building on its own, with the model stood in for."""
    import sentence_reading.llm.hear_waveform as hw

    monkeypatch.setattr(hw, "sound_score_of", lambda sheet, groups: got)
    return _slot_certainty(FakeSheet([[0.0, 0.0]]), asked)


def test_the_answer_carries_every_sound_on_its_own(monkeypatch):
    """design/384 - the word score cannot say which sound was missing."""
    got = _rows_from(monkeypatch, [
        {"sure": 0.80, "low": 0.11, "n": 3.0, "said": 3.0, "sym": 0.80,
         "each": [0.95, 0.88, 0.11]},
        None,
        {"sure": 0.76, "low": 0.72, "n": 2.0, "said": 3.0, "sym": 0.507,
         "each": [0.80, 0.72]},
    ])

    assert got["sure_code"] == "ok"
    # Words barred apart, sounds inside spaced, a dash for the word with none.
    assert got["slot_each"] == "95 88 11|-|80 72"
    # The bars count the words, so the rows stay readable side by side.
    assert len(got["slot_each"].split("|")) == len(got["slot_sym"].split())


def test_the_per_sound_row_counts_the_same_words_as_the_score_row(monkeypatch):
    got = _rows_from(monkeypatch, [None, None], asked="a b c | d e f")

    assert got["slot_each"] == "-|-"
    assert got["slot_sym"] == "- -"


def test_the_per_sound_row_survives_the_evidence_sanitizer(monkeypatch):
    """A bar is not a letter, so the allow list has to carry this key."""
    got = _rows_from(monkeypatch, [
        {"sure": 0.80, "low": 0.11, "n": 3.0, "said": 3.0, "sym": 0.80,
         "each": [0.95, 0.88, 0.11]},
    ], asked="a b c")

    kept = _safe_details({"slot_each": got["slot_each"]})

    assert kept.get("slot_each") == "95 88 11"


def test_a_failed_alignment_leaves_the_per_sound_row_empty(monkeypatch):
    got = _rows_from(monkeypatch, None, asked="a b c")

    assert got["sure_code"] == "no_align"
    assert got["slot_each"] == ""
