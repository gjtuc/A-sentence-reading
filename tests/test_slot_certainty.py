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
