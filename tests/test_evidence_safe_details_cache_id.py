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
