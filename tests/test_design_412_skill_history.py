"""design/412 - the skill store keeps what the phone sends, plus the rung history."""

from __future__ import annotations

from sentence_reading.llm.practice_gcs import (
    SKILL_HISTORY_MAX,
    merge_skill_stores,
    normalize_skill_store,
)


def _phone(**over):
    base = {
        "tier": 3,
        "density": 0,
        "pinned": True,
        "saved_tier": 2,
        "saved_density": 0,
        "line_avg": 0.73,
        "line_var": 0.02,
        "line_n": 1300,
        "line_unit": 1,
        "ladder_fix": 1,
        "history": [
            {"at": 10, "why": "sample_on", "t0": 2, "d0": 0, "t1": 3, "d1": 0, "n": 0, "lo": 0.85, "hi": 0.95},
        ],
        "updated_at_ms": 100,
        "days": {},
    }
    base.update(over)
    return base


def test_nothing_the_phone_sends_is_dropped():
    s = normalize_skill_store(_phone())
    # Before design/412 these seven came back missing, and the phone saved the
    # reply over its own copy.
    assert s["pinned"] is True
    assert s["saved_tier"] == 2
    assert s["saved_density"] == 0
    assert s["line_n"] == 1300
    assert s["line_unit"] == 1
    assert abs(s["line_avg"] - 0.73) < 1e-9
    assert s["ladder_fix"] == 1
    assert s["history"][0]["why"] == "sample_on"


def test_a_store_with_no_line_says_so_rather_than_inventing_one():
    s = normalize_skill_store({"tier": 2})
    assert "line_unit" not in s
    assert s["pinned"] is False
    assert s["saved_tier"] == -1
    assert s["history"] == []


def test_history_is_the_union_oldest_first():
    a = _phone(updated_at_ms=200)
    b = _phone(
        updated_at_ms=50,
        history=[
            {"at": 5, "why": "hold", "t0": 2, "d0": 0, "t1": 2, "d1": 0, "avg": 0.9, "n": 6},
            {"at": 10, "why": "sample_on", "t0": 2, "d0": 0, "t1": 3, "d1": 0},
        ],
    )
    m = merge_skill_stores(a, b)
    assert [(r["at"], r["why"]) for r in m["history"]] == [(5, "hold"), (10, "sample_on")]
    assert m["history"][0]["avg"] == 0.9


def test_an_old_client_does_not_wipe_the_line_or_the_fix():
    server = normalize_skill_store(_phone(updated_at_ms=100))
    old_phone = {"tier": 3, "density": 1, "updated_at_ms": 300, "days": {}}
    m = merge_skill_stores(server, old_phone)
    assert m["tier"] == 3 and m["density"] == 1
    assert m["line_n"] == 1300
    assert m["ladder_fix"] == 1
    assert len(m["history"]) == 1
    # Missing means not pinned: carrying an old pin over would hold the rung.
    assert m["pinned"] is False


def test_history_rows_are_checked_and_capped():
    rows = [{"at": i + 1, "why": "hold", "t0": 2, "d0": 0, "t1": 2, "d1": 0} for i in range(SKILL_HISTORY_MAX + 30)]
    rows += [
        {"at": 0, "why": "hold"},
        {"at": 5, "why": "Bad Reason!"},
        {"at": 7, "why": "tier_up", "t0": 99, "d0": -9},
        "junk",
    ]
    s = normalize_skill_store({"history": rows})
    assert len(s["history"]) == SKILL_HISTORY_MAX
    assert s["history"][-1]["at"] == SKILL_HISTORY_MAX + 30
    assert all(r["why"] == "hold" for r in s["history"])
    clamped = normalize_skill_store({"history": rows[-2:-1]})["history"][0]
    assert clamped["t0"] == 9 and clamped["d0"] == -2
