"""design/250 — practice focus + skill cloud sync merge + route contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sentence_reading.llm.practice_gcs import (
    empty_focus_store,
    empty_skill_store,
    merge_focus_stores,
    merge_skill_stores,
    normalize_focus_store,
    normalize_skill_store,
)


def test_merge_focus_max_blocks_and_streak():
    a = {"version": 2, "days": {"2026-09-01": 1, "2026-09-02": 2}, "best_streak": 1, "updated_at_ms": 10}
    b = {"version": 2, "days": {"2026-09-01": 3}, "best_streak": 4, "updated_at_ms": 20}
    m = merge_focus_stores(a, b)
    assert m["days"]["2026-09-01"] == 3
    assert m["days"]["2026-09-02"] == 2
    assert m["best_streak"] == 4
    assert m["updated_at_ms"] == 20


def test_merge_skill_days_prefer_larger_n_live_lww():
    a = {
        "tier": 1,
        "density": -1,
        "updated_at_ms": 10,
        "days": {"2026-09-01": {"n": 5, "sum": 4.0}},
        "epoch_means": [0.8],
        "epoch_target_n": 6,
    }
    b = {
        "tier": 4,
        "density": 1,
        "updated_at_ms": 50,
        "days": {"2026-09-01": {"n": 2, "sum": 1.9}},
        "epoch_means": [],
        "epoch_target_n": 8,
    }
    m = merge_skill_stores(a, b)
    assert m["days"]["2026-09-01"]["n"] == 5
    assert m["days"]["2026-09-01"]["sum"] == 4.0
    assert m["tier"] == 4
    assert m["density"] == 1
    assert m["epoch_target_n"] == 8
    assert m["updated_at_ms"] == 50


def test_normalize_missing_updated_at():
    f = normalize_focus_store({"days": {"2026-09-01": 1}, "best_streak": 1})
    assert f["updated_at_ms"] == 0
    s = normalize_skill_store({"tier": 2, "days": {}})
    assert s["updated_at_ms"] == 0
    s9 = normalize_skill_store({"tier": 9, "days": {}})
    assert s9["tier"] == 9
    s_over = normalize_skill_store({"tier": 99, "days": {}})
    assert s_over["tier"] == 9
    assert empty_focus_store()["version"] == 2
    assert empty_skill_store()["tier"] == 2


def test_practice_sync_routes_exist():
    from sentence_reading.api.app import app

    client = TestClient(app)
    # Unauthenticated soft responses (no crash).
    for path in ("/api/practice/focus/sync", "/api/practice/skill/sync"):
        r = client.get(path)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        # available may be false without GCS/auth
        assert "available" in body


def test_focus_blocks_from_two_devices_add_up_509() -> None:
    day = "2026-11-03"
    phone = {"days": {day: 3}, "by_dev": {"PHONEdevice01": {day: 3}}, "best_streak": 1}
    web = {"days": {day: 2}, "by_dev": {"WEBwindow0001": {day: 2}}, "best_streak": 1}
    merged = merge_focus_stores(phone, web)
    assert merged["days"][day] == 5
    assert merged["by_dev"] == {"PHONEdevice01": {day: 3}, "WEBwindow0001": {day: 2}}
    again = merge_focus_stores(merged, {"days": {day: 3}, "by_dev": {"PHONEdevice01": {day: 4}}})
    assert again["days"][day] == 6


def test_focus_store_without_devices_is_unchanged_509() -> None:
    old = {"days": {"2026-10-10": 2}, "best_streak": 7, "updated_at_ms": 5}
    out = normalize_focus_store(old)
    assert out == {"version": 2, "days": {"2026-10-10": 2}, "best_streak": 7, "updated_at_ms": 5}
    assert merge_focus_stores(old, {"by_dev": {"PHONEdevice01": {"2026-10-10": 1}}})["days"]["2026-10-10"] == 2


def test_focus_store_drops_bad_device_ids_509() -> None:
    out = normalize_focus_store(
        {"by_dev": {"short": {"2026-11-03": 1}, "bad id!!": {"2026-11-03": 1}, "PHONEdevice01": {"nope": 3}}}
    )
    assert "by_dev" not in out
    assert out["days"] == {}


def test_practice_cursor_key_is_a_valid_spot_id_509() -> None:
    from sentence_reading.llm import reading_spots

    assert reading_spots.valid_cache_id("p.7d506b60fb6b")
