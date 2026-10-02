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


def test_no_reference_says_so():
    assert _slot_certainty(None, "") == ("", "", "no_target")
    assert _slot_certainty(None, "  |  ") == ("", "", "no_target")


def test_a_reference_without_a_sheet_says_so():
    assert _slot_certainty(None, "a b c") == ("", "", "no_sheet")


def test_a_sheet_that_throws_does_not_take_the_take_down():
    class Boom:
        def __getitem__(self, key):
            raise RuntimeError("no")

    sure, floor, code = _slot_certainty(Boom(), "a b c")
    assert sure == ""
    assert floor == ""
    assert code != "ok"


def test_slot_sure_is_digits_and_dashes_only(monkeypatch):
    # Two words, the second one unaskable.
    monkeypatch.setattr(
        "sentence_reading.llm.hear_waveform.certainty_of",
        lambda sheet, groups: [[0.9, 0.8], []],
    )
    sure, floor, code = _slot_certainty(FakeSheet([[0.0]]), "x y | z")
    assert code == "ok"
    assert sure == "85 -"
    assert floor == "8000 -"
    for field in (sure, floor):
        assert set(field) <= set("0123456789 -")


def test_the_row_survives_sanitising():
    out = _safe_details({"slot_sure": "85 90 -", "slot_floor": "8000 12 -"})
    assert out["slot_sure"] == "85 90 -"
    assert out["slot_floor"] == "8000 12 -"


def test_a_real_sheet_lines_up_with_the_words_sent(monkeypatch):
    """One group per `|`, in order, even when the model knows none of a group."""
    seen: list[list[list[str]]] = []

    def fake(sheet, groups):
        seen.append(groups)
        return [[1.0] for _ in groups]

    monkeypatch.setattr(
        "sentence_reading.llm.hear_waveform.certainty_of", fake
    )
    sure, floor, code = _slot_certainty(FakeSheet([[0.0]]), "a b | c | d e f")
    assert code == "ok"
    assert seen == [[["a", "b"], ["c"], ["d", "e", "f"]]]
    assert sure == "100 100 100"
    assert floor == "10000 10000 10000"
