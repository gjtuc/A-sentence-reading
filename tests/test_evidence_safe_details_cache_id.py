"""design/284 — digit-leading cache ids must be prefixed for details."""
from __future__ import annotations

from sentence_reading.llm.evidence_bus import _safe_details, detail_cache_id


def test_digit_leading_cache_id_dropped_without_prefix() -> None:
    assert _safe_details({"winner_id": "45efe205811d"}) == {}


def test_digit_leading_cache_id_kept_with_c_prefix() -> None:
    wid = detail_cache_id("45efe205811d")
    assert wid == "c45efe205811d"
    out = _safe_details({"winner_id": wid, "deleted_n": 3})
    assert out == {"winner_id": "c45efe205811d", "deleted_n": 3}


def test_letter_leading_still_ok() -> None:
    out = _safe_details({"winner_id": "abcdef012345"})
    assert out.get("winner_id") == "abcdef012345"


def test_slot_scores_survives_sanitising():
    """design/377 - the closeness string has to reach the log to be of any use.

    It is digits, spaces and dashes, so the snake-token rule would drop it. It is
    on the free-text list instead, beside `slot_pieces`, which already carries the
    printed words, so this adds no paper text to the stream.
    """
    out = _safe_details({"slot_scores": "40 100 -  56 60", "slot_hits": "01-00"})
    assert out["slot_scores"] == "40 100 - 56 60"
    assert out["slot_hits"] == "01-00"


def test_slot_scores_is_capped_like_its_neighbours():
    """A sentence long enough to overrun the cap loses its tail, not the key."""
    out = _safe_details({"slot_scores": " ".join(["100"] * 300)})
    assert len(out["slot_scores"]) == 400

