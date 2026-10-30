# -*- coding: utf-8 -*-
"""design/493 — server-held upload queue (one job at a time, app may be closed)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asr_versions import assert_at_least
from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_jobs_gcs as ij
from sentence_reading.llm import ingest_queue as iq
from sentence_reading.llm.ingest_stall import sweep_candidate

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "493-server-upload-queue.md"

UID = "u_queue_owner"


@pytest.fixture()
def cas_bucket(monkeypatch: pytest.MonkeyPatch):
    bucket: dict[str, tuple[bytes, int]] = {}

    def down(name: str, *, meter: bool = True):
        got = bucket.get(name)
        return (got[0], got[1]) if got else (None, 0)

    def up(name, data, *, if_generation_match, content_type="", meter=True):
        cur = bucket.get(name)
        gen = cur[1] if cur else 0
        if gen != int(if_generation_match):
            return "conflict"
        bucket[name] = (bytes(data), gen + 1)
        return "ok"

    monkeypatch.setenv("ASR_GCS_BUCKET", "fake-bucket")
    monkeypatch.setattr(iq, "download_bytes_generation", down)
    monkeypatch.setattr(iq, "upload_bytes_generation_match", up)
    agu.reset_gcs_uid()
    yield bucket
    agu.reset_gcs_uid()


def _jid(n: int) -> str:
    return f"job_{n:012x}"


def test_append_keeps_order_and_skips_duplicates(cas_bucket):
    assert iq.append_job(UID, _jid(1), filename="a.pdf", content_hash="a" * 64) == 0
    assert iq.append_job(UID, _jid(2), filename="b.pdf") == 1
    assert iq.append_job(UID, _jid(1), filename="a.pdf") == 0
    items = iq.load_queue(UID)
    assert [x["job_id"] for x in items] == [_jid(1), _jid(2)]
    assert items[0]["content_hash"] == "a" * 64
    obj = iq.queue_object(UID)
    assert obj and "ingest_queue" in obj and UID in obj


def test_mutate_retries_after_a_lost_race(cas_bucket, monkeypatch: pytest.MonkeyPatch):
    iq.append_job(UID, _jid(1))
    real_up = iq.upload_bytes_generation_match
    calls = {"n": 0}

    def racing_up(name, data, *, if_generation_match, content_type="", meter=True):
        calls["n"] += 1
        if calls["n"] == 1:
            # another instance appends first
            raw, gen = cas_bucket[name]
            cas_bucket[name] = (
                iq._encode([*iq.parse_queue(raw), {"job_id": _jid(9), "filename": "", "content_hash": "", "at": ""}]),
                gen + 1,
            )
        return real_up(name, data, if_generation_match=if_generation_match, content_type=content_type, meter=meter)

    monkeypatch.setattr(iq, "upload_bytes_generation_match", racing_up)
    assert iq.append_job(UID, _jid(2)) == 2
    assert [x["job_id"] for x in iq.load_queue(UID)] == [_jid(1), _jid(9), _jid(2)]


def test_plan_starts_the_first_waiting_job_after_dropping_finished():
    items = [{"job_id": _jid(i), "filename": "", "content_hash": "", "at": ""} for i in (1, 2, 3)]
    jobs = {
        _jid(1): {"done": True},
        _jid(2): {"queue_waiting": True},
        _jid(3): {"queue_waiting": True},
    }
    loaded: list[str] = []

    def load(jid):
        loaded.append(jid)
        return jobs.get(jid)

    plan = iq.plan_advance(items, load)
    assert plan["action"] == "start"
    assert plan["job_id"] == _jid(2)
    assert plan["drop"] == [_jid(1)]
    assert loaded == [_jid(1), _jid(2)]
    assert iq.ahead_counts(items, plan["drop"]) == {_jid(2): 0, _jid(3): 1}


def test_plan_waits_while_the_head_runs_and_reclaims_a_dead_head():
    now = datetime(2026, 10, 30, tzinfo=timezone.utc)
    items = [{"job_id": _jid(i), "filename": "", "content_hash": "", "at": ""} for i in (1, 2)]
    alive = {"lease_until": (now + timedelta(seconds=60)).isoformat()}
    dead = {"lease_until": (now - timedelta(seconds=60)).isoformat()}
    fresh = {"queue_started_at": (now - timedelta(seconds=10)).isoformat()}
    stale = {"queue_started_at": (now - timedelta(seconds=600)).isoformat()}
    waiting = {"queue_waiting": True}

    def plan(head):
        return iq.plan_advance(items, {_jid(1): head, _jid(2): waiting}.get, now=now)

    assert plan(alive)["action"] == "busy"
    assert plan(dead)["action"] == "reclaim"
    assert plan(fresh)["action"] == "busy"
    assert plan(stale)["action"] == "reclaim"
    assert plan({**dead, "_local_running": True})["action"] == "busy"
    assert plan(None)["action"] == "start"
    assert plan({"cancel_requested": True})["job_id"] == _jid(2)


def test_waiting_message_counts_jobs_ahead():
    assert iq.waiting_message(0) == iq.WAITING_MESSAGE
    assert iq.waiting_message(None) == iq.WAITING_MESSAGE
    assert "2" in iq.waiting_message(2)


def test_kill_switch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_INGEST_SERVER_QUEUE", "0")
    assert iq.server_queue_enabled() is False
    monkeypatch.delenv("ASR_INGEST_SERVER_QUEUE")
    assert iq.server_queue_enabled() is True


@pytest.fixture()
def queue_env(cas_bucket, monkeypatch: pytest.MonkeyPatch):
    bucket: dict[str, bytes] = {}

    def upload(name: str, data: bytes, *, content_type: str = "", meter: bool = True) -> bool:
        bucket[name] = bytes(data)
        return True

    def download(name: str, *, meter: bool = True) -> bytes | None:
        return bucket.get(name)

    def delete(name: str) -> bool:
        return bucket.pop(name, None) is not None

    monkeypatch.setenv("ASR_INGEST_JOB_RECLAIM", "1")
    monkeypatch.setenv("ASR_INGEST_INLINE", "1")
    monkeypatch.delenv("ASR_INGEST_SERVER_QUEUE", raising=False)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.upload_bytes", upload)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.download_bytes", download)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.delete_bytes", delete)
    monkeypatch.setattr(ij, "upload_bytes", upload)
    monkeypatch.setattr(ij, "download_bytes", download)
    monkeypatch.setattr(ij, "delete_bytes", delete)
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.sweep_index_absent_paper_prefixes",
        lambda: None,
    )
    started: list[str] = []

    async def fake_run(job_id, tmp_path, filename, kind, **kwargs):
        started.append(job_id)

    monkeypatch.setattr(app_mod, "_run_ingest_job", fake_run)
    monkeypatch.setattr(app_mod, "_kick_ingest_queue", lambda uid, *, why: None)
    app_mod._JOBS.clear()
    app_mod._QUEUE_UIDS.clear()
    app_mod._QUEUE_AHEAD.clear()
    yield started
    app_mod._JOBS.clear()
    app_mod._QUEUE_UIDS.clear()
    app_mod._QUEUE_AHEAD.clear()


def _begin(n: int, *, queue: bool = True) -> dict:
    return app_mod._begin_ingest_from_bytes(
        b"%PDF-1.4 queue " + str(n).encode(),
        f"paper{n}.pdf",
        "pdf",
        owner_uid=UID,
        queue=queue,
    )


def test_server_queue_runs_one_job_at_a_time(queue_env):
    started = queue_env

    async def main() -> None:
        a = _begin(1)
        b = _begin(2)
        assert a["queued"] is True and b["queued"] is True
        assert (a["queue_position"], b["queue_position"]) == (0, 1)
        ja, jb = a["job_id"], b["job_id"]
        assert started == []
        assert ij.load_ingest_job(jb, owner_uid=UID)["queue_waiting"] is True

        plan = await app_mod._advance_ingest_queue(UID, why="test")
        await asyncio.sleep(0)
        assert (plan["action"], plan["job_id"]) == ("start", ja)
        assert started == [ja]
        assert ij.load_ingest_job(ja, owner_uid=UID)["queue_waiting"] is False
        assert ij.load_ingest_job(jb, owner_uid=UID)["queue_waiting"] is True
        assert app_mod._QUEUE_AHEAD[UID] == {ja: 0, jb: 1}

        plan = await app_mod._advance_ingest_queue(UID, why="test")
        assert plan["action"] == "busy"
        assert started == [ja]

        done = ij.load_ingest_job(ja, owner_uid=UID)
        done.update({"done": True, "result": {"ok": True, "cache_id": "c1"}})
        assert ij.save_ingest_job(ja, done)
        plan = await app_mod._advance_ingest_queue(UID, why="test")
        await asyncio.sleep(0)
        assert (plan["action"], plan["job_id"]) == ("start", jb)
        assert started == [ja, jb]
        assert [x["job_id"] for x in iq.load_queue(UID)] == [jb]

    asyncio.run(main())


def test_waiting_job_is_never_started_by_reclaim_or_sweep(queue_env):
    started = queue_env

    async def main() -> None:
        _begin(1)
        jb = _begin(2)["job_id"]
        tok, reason = ij.try_claim_lease_with_reason(jb, owner_uid=UID)
        assert tok is None and reason == "queue_waiting"
        assert sweep_candidate(app_mod._JOBS[jb]) == "none"
        assert ij.job_is_stuck(app_mod._JOBS[jb]) == (False, "")
        view = ij.public_job_view(jb, ij.load_ingest_job(jb, owner_uid=UID))
        assert view["queue_waiting"] is True
        assert view["worker_alive"] is True
        assert view["stage"] == "waiting"
        assert await app_mod._reclaim_ingest_job_from_gcs(jb, UID) is False
        await asyncio.sleep(0)
        assert started == []

    asyncio.run(main())


def test_cancelled_and_failed_jobs_leave_the_line(queue_env):
    started = queue_env

    async def main() -> None:
        ja = _begin(1)["job_id"]
        jb = _begin(2)["job_id"]
        jc = _begin(3)["job_id"]
        await app_mod._advance_ingest_queue(UID, why="test")
        await asyncio.sleep(0)
        failed = ij.load_ingest_job(ja, owner_uid=UID)
        failed.update({"done": True, "error": "boom"})
        assert ij.save_ingest_job(ja, failed)
        app_mod._wipe_ingest_artifacts(jb, owner_uid=UID, filename="paper2.pdf")
        plan = await app_mod._advance_ingest_queue(UID, why="test")
        await asyncio.sleep(0)
        assert (plan["action"], plan["job_id"]) == ("start", jc)
        assert set(plan["drop"]) == {ja, jb}
        assert started == [ja, jc]

    asyncio.run(main())


def test_a_dead_started_head_is_reclaimed(queue_env):
    started = queue_env

    async def main() -> None:
        ja = _begin(1)["job_id"]
        _begin(2)
        await app_mod._advance_ingest_queue(UID, why="test")
        await asyncio.sleep(0)
        dead = ij.load_ingest_job(ja, owner_uid=UID)
        old = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat()
        dead.update({"lease_until": old, "queue_started_at": old})
        assert ij.save_ingest_job(ja, dead)
        app_mod._JOBS.pop(ja, None)
        plan = await app_mod._advance_ingest_queue(UID, why="test")
        await asyncio.sleep(0)
        assert (plan["action"], plan["job_id"]) == ("reclaim", ja)
        assert started == [ja, ja]

    asyncio.run(main())


def test_queue_write_failure_or_kill_switch_starts_at_once(queue_env, monkeypatch: pytest.MonkeyPatch):
    started = queue_env

    async def main() -> None:
        monkeypatch.setattr(iq, "append_job", lambda *a, **k: -1)
        out = _begin(1)
        await asyncio.sleep(0)
        assert "queued" not in out
        assert started == [out["job_id"]]
        assert app_mod._JOBS[out["job_id"]].get("queue_waiting") is False
        monkeypatch.setenv("ASR_INGEST_SERVER_QUEUE", "0")
        out2 = _begin(2)
        await asyncio.sleep(0)
        assert "queued" not in out2
        assert started == [out["job_id"], out2["job_id"]]
        out3 = _begin(3, queue=False)
        await asyncio.sleep(0)
        assert "queued" not in out3

    asyncio.run(main())


def test_status_flag_and_doc():
    st = TestClient(app).get("/api/status").json()
    assert_at_least(st["version"], "0.3.506")
    assert st["ingest_server_queue"] is True
    text = DESIGN.read_text(encoding="utf-8")
    assert "queue_waiting" in text and "0.3.506" in text


def test_queue_query_flag_and_fresh_start_message(queue_env):
    from types import SimpleNamespace

    assert app_mod._want_queue(SimpleNamespace(query_params={"queue": "1"})) is True
    assert app_mod._want_queue(SimpleNamespace(query_params={})) is False

    async def main() -> None:
        ja = _begin(1)["job_id"]
        await app_mod._advance_ingest_queue(UID, why="test")
        assert app_mod._JOBS[ja]["message"] == "시작해요"
        assert app_mod._JOBS[ja]["queue_member"] is True

    asyncio.run(main())
