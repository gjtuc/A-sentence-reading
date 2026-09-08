# -*- coding: utf-8 -*-
"""design/184 — ingest intermediate artifact TTL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from sentence_reading.llm import ingest_artifact_ttl as ttl


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_stamp_once_on_terminal() -> None:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    job: dict[str, Any] = {"done": True, "error": None}
    assert ttl.stamp_terminal_retention(job, now=now) is True
    until = job["artifact_retain_until"]
    assert ttl.stamp_terminal_retention(job, now=now + timedelta(hours=1)) is False
    assert job["artifact_retain_until"] == until
    assert job["artifact_retain_reason"] == "terminal_ok"


def test_stamp_skips_non_terminal() -> None:
    job = {"done": False, "error": None, "lease_until": _iso(datetime.now(timezone.utc))}
    assert ttl.stamp_terminal_retention(job) is False
    assert "artifact_retain_until" not in job


def test_should_purge_terminal_after_ttl() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    job = {
        "done": True,
        "artifact_retain_until": _iso(now - timedelta(hours=1)),
        "artifact_retain_reason": "terminal_ok",
    }
    ok, reason = ttl.should_purge_job(job, now=now, has_upload=True)
    assert ok is True
    assert reason == "terminal_ok"


def test_should_keep_terminal_before_ttl() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    job = {
        "done": True,
        "artifact_retain_until": _iso(now + timedelta(hours=10)),
    }
    ok, reason = ttl.should_purge_job(job, now=now, has_upload=True)
    assert ok is False
    assert reason == "not_yet"


def test_reclaim_upload_kept() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    job = {
        "done": False,
        "error": None,
        "lease_until": _iso(now - timedelta(hours=1)),
        "updated_at": _iso(now - timedelta(hours=500)),
    }
    ok, reason = ttl.should_purge_job(job, now=now, has_upload=True)
    assert ok is False
    assert reason == "reclaim_upload"


def test_lease_alive_kept() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    job = {
        "done": False,
        "error": None,
        "lease_until": _iso(now + timedelta(minutes=5)),
    }
    ok, reason = ttl.should_purge_job(job, now=now, has_upload=False)
    assert ok is False
    assert reason == "lease_alive"


def test_abandoned_no_upload_purge() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    job = {
        "done": False,
        "error": None,
        "lease_until": _iso(now - timedelta(hours=1)),
        "updated_at": _iso(now - timedelta(hours=ttl.abandon_hours() + 1)),
    }
    ok, reason = ttl.should_purge_job(job, now=now, has_upload=False)
    assert ok is True
    assert reason == "abandoned_no_upload"


def test_assert_deletable_refuses_papers() -> None:
    uid = "uid_test_184"
    papers = f"asr/users/{uid}/papers/abc123/source.pdf"
    assert ttl.assert_deletable_object(papers, uid=uid) is None
    upload = f"asr/users/{uid}/ingest_uploads/jobabc123def.pdf"
    assert ttl.assert_deletable_object(upload, uid=uid) == upload
    wrong_uid = f"asr/users/otheruid/ingest_uploads/jobabc123def.pdf"
    assert ttl.assert_deletable_object(wrong_uid, uid=uid) is None


def test_clear_retention_on_reclaim() -> None:
    job = {
        "artifact_retain_until": "x",
        "artifact_retain_reason": "terminal_ok",
        "artifact_purge_partial": True,
    }
    ttl.clear_retention_on_reclaim(job)
    assert "artifact_retain_until" not in job
    assert "artifact_retain_reason" not in job
    assert "artifact_purge_partial" not in job


def test_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_INGEST_ARTIFACT_TTL", "0")
    assert ttl.artifact_ttl_enabled() is False
    summary = ttl.purge_uid("uid_whatever")
    assert summary["examined"] == 0
    assert summary["purged_jobs"] == 0


def test_delete_order_and_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_delete(name: str) -> bool:
        calls.append(name)
        return True

    monkeypatch.setenv("ASR_INGEST_ARTIFACT_TTL_DRY_RUN", "0")
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.delete_bytes", fake_delete, raising=False
    )
    monkeypatch.setattr(
        "sentence_reading.llm.ingest_jobs_gcs.ingest_upload_object",
        lambda jid, suffix=".pdf", uid=None: (
            f"asr/users/{uid}/ingest_uploads/{jid}{suffix}"
            if suffix == ".pdf"
            else None
        ),
    )
    monkeypatch.setattr(
        "sentence_reading.llm.ingest_jobs_gcs.ingest_payload_object",
        lambda jid, uid=None: f"asr/users/{uid}/ingest_payloads/{jid}.json",
    )
    monkeypatch.setattr(
        "sentence_reading.llm.ingest_jobs_gcs.ingest_job_object",
        lambda jid, uid=None: f"asr/users/{uid}/ingest_jobs/{jid}.json",
    )

    # dry-run: no deletes
    out = ttl.delete_job_artifacts(
        "jobabc12", owner_uid="uid_test_184", dry_run=True
    )
    assert out["dry_run"] is True
    assert calls == []
    assert out["counts"]["dry_run"] >= 1

    out2 = ttl.delete_job_artifacts(
        "jobabc12", owner_uid="uid_test_184", dry_run=False
    )
    assert out2["ok"] is True
    assert len(calls) == 3
    assert "ingest_uploads" in calls[0]
    assert "ingest_payloads" in calls[1]
    assert "ingest_jobs" in calls[2]


def test_serialize_persists_retain_fields() -> None:
    from sentence_reading.llm.ingest_jobs_gcs import serialize_job_record

    job = {
        "owner_uid": "u1",
        "done": True,
        "artifact_retain_until": "2026-09-15T00:00:00+00:00",
        "artifact_retain_reason": "terminal_ok",
    }
    out = serialize_job_record("jobabc12xyz", job)
    assert out["artifact_retain_until"].startswith("2026-09-15")
    assert out["artifact_retain_reason"] == "terminal_ok"


def test_status_flags() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.178"
    assert st.get("ingest_artifact_ttl") is True
    assert int(st.get("ingest_artifact_ttl_hours") or 0) == 168
    assert st.get("ingest_artifact_ttl_dry_run") is False
