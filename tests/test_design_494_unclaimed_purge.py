"""design/494 — server papers no phone pulled leave after 30 days, per owner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from sentence_reading.llm import paper_handoff as ph
from sentence_reading.llm import papers_gcs as pg

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _entry(cid: str, days_old: float) -> dict:
    return {"id": cid, "title": "t", "updated_at": _iso(NOW - timedelta(days=days_old))}


@pytest.fixture
def owner_env(monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.llm.auth_google import current_gcs_uid

    indexes: dict[str, list[dict]] = {}
    states: dict[str, dict] = {}
    wiped: list[tuple[str, str, str]] = []

    monkeypatch.setattr(ph, "handoff_enabled", lambda: True)
    monkeypatch.delenv("ASR_PAPER_UNCLAIMED_PURGE", raising=False)
    monkeypatch.delenv("ASR_PAPER_UNCLAIMED_DAYS", raising=False)
    monkeypatch.delenv("ASR_PAPER_HANDOFF_ABANDON_DRY_RUN", raising=False)
    monkeypatch.setattr(
        pg, "papers_index_object", lambda: f"users/{current_gcs_uid()}/papers_index.json"
    )

    def fake_download(obj: str):
        uid = obj.split("/")[1]
        rows = indexes.get(uid)
        if rows is None:
            return None
        return json.dumps({"entries": rows}).encode("utf-8")

    monkeypatch.setattr(pg, "download_bytes", fake_download)
    monkeypatch.setattr(ph, "load_handoff_state", lambda cid: states.get(cid))

    def fake_abandon(cid: str, *, reason: str = "abandon_ttl"):
        wiped.append((str(current_gcs_uid()), cid, reason))
        return {"ok": True}

    monkeypatch.setattr(ph, "abandon_one", fake_abandon)
    return indexes, states, wiped


def test_should_purge_unclaimed_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_PAPER_UNCLAIMED_DAYS", raising=False)
    assert ph.unclaimed_days() == 30
    assert ph.should_purge_unclaimed(_entry("a" * 8, 31), now=NOW) == (True, "unclaimed_ttl")
    assert ph.should_purge_unclaimed(_entry("a" * 8, 29), now=NOW) == (False, "not_yet")
    assert ph.should_purge_unclaimed({"id": "x"}, now=NOW) == (False, "no_timestamp")
    assert ph.should_purge_unclaimed(None, now=NOW) == (False, "bad_entry")
    monkeypatch.setenv("ASR_PAPER_UNCLAIMED_DAYS", "7")
    assert ph.should_purge_unclaimed(_entry("a" * 8, 8), now=NOW)[0] is True
    monkeypatch.setenv("ASR_PAPER_UNCLAIMED_DAYS", "junk")
    assert ph.unclaimed_days() == 30


def test_purge_wipes_only_old_rows_for_the_bound_owner(owner_env) -> None:
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid

    indexes, _states, wiped = owner_env
    indexes["user001"] = [_entry("old00001", 40), _entry("new00001", 3)]
    with _with_uid("user001"):
        out = ph.purge_unclaimed_once(now=NOW)
    assert out["examined"] == 2
    assert out["purged"] == 1
    assert out["skipped"] == 1
    assert wiped == [("user001", "old00001", "unclaimed_ttl")]


def test_pending_pull_in_progress_is_kept(owner_env) -> None:
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid

    indexes, states, wiped = owner_env
    indexes["user001"] = [_entry("pull0001", 40)]
    states["pull0001"] = {"pending": True, "manifest_built_at": _iso(NOW - timedelta(hours=1))}
    with _with_uid("user001"):
        out = ph.purge_unclaimed_once(now=NOW)
    assert out["purged"] == 0
    assert wiped == []


def test_all_owners_each_bound_in_turn(owner_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from sentence_reading.llm import ingest_artifact_ttl as ttl
    from sentence_reading.llm.auth_google import current_gcs_uid

    indexes, _states, wiped = owner_env
    indexes["user001"] = [_entry("old00001", 40)]
    indexes["user002"] = [_entry("old00002", 31), _entry("new00002", 1)]
    monkeypatch.setattr(ttl, "discover_owner_uids", lambda: ["user001", "user002", "user003"])
    seen: list[str | None] = []
    monkeypatch.setattr(
        ph,
        "purge_abandoned_once",
        lambda **_k: seen.append(current_gcs_uid()) or {"examined": 0, "purged": 0},
    )
    out = ph.purge_all_owners_once(now=NOW)
    assert seen == ["user001", "user002", "user003"]
    assert out["owners"] == 3
    assert out["unclaimed_purged"] == 2
    assert sorted(w[:2] for w in wiped) == [("user001", "old00001"), ("user002", "old00002")]


def test_kill_switch_and_dry_run(owner_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid

    indexes, _states, wiped = owner_env
    indexes["user001"] = [_entry("old00001", 40)]
    monkeypatch.setenv("ASR_PAPER_UNCLAIMED_PURGE", "0")
    with _with_uid("user001"):
        assert ph.purge_unclaimed_once(now=NOW)["examined"] == 0
    monkeypatch.delenv("ASR_PAPER_UNCLAIMED_PURGE")
    monkeypatch.setattr(ph, "abandon_ttl_dry_run", lambda: True)
    with _with_uid("user001"):
        out = ph.purge_unclaimed_once(now=NOW)
    assert out["purged"] == 1 and out["dry_run"] is True
    assert wiped == []


def test_loop_and_retention_wiring() -> None:
    import os

    from sentence_reading.llm import paper_retention as pr

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_src = open(
        os.path.join(root, "src", "sentence_reading", "api", "app.py"), encoding="utf-8"
    ).read()
    i = app_src.find("async def _paper_handoff_abandon_loop")
    assert i > 0
    body = app_src[i : i + 2500]
    assert "purge_all_owners_once" in body
    assert "unclaimed_purged" in body
    old = os.environ.pop("ASR_PAPER_RETENTION", None)
    try:
        assert pr.retention_enabled() is False
    finally:
        if old is not None:
            os.environ["ASR_PAPER_RETENTION"] = old
