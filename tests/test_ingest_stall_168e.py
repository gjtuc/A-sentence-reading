# -*- coding: utf-8 -*-
"""design/168e — stall detector, stuck/integrity admin, sweeper helpers."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import evidence_bus as eb
from sentence_reading.llm import ingest_jobs_gcs as ij
from sentence_reading.llm import ingest_stall as stall
from sentence_reading.llm import ops_events as oev
from sentence_reading.llm.auth_google import AuthUser, issue_session_token
from sentence_reading.llm.ingest_integrity import Violation, violations_to_public


@pytest.fixture()
def ops_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_OPS_EVENTS", "1")
    monkeypatch.setenv("ASR_INGEST_STALL_SEC", "300")
    monkeypatch.setenv("ASR_INGEST_SWEEPER_SEC", "60")
    monkeypatch.setattr(oev, "local_events_path", lambda: tmp_path / "ops_events.jsonl")
    monkeypatch.setattr(oev, "_gcs_events_object", lambda: None)
    return tmp_path


@pytest.fixture()
def ev_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})
    return tmp_path


def _admin_client(monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "168e-test-secret")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    user = AuthUser(
        uid="uid_admin_168e",
        email="admin@example.com",
        name="Admin",
        picture="",
    )
    token = issue_session_token(user)
    return TestClient(app), token


def test_status_stall_pin(ops_tmp) -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.156"
    assert st.get("ingest_stall_detector") is True


def test_status_stall_kill(ops_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_INGEST_STALL_SEC", "0")
    st = TestClient(app).get("/api/status").json()
    assert st.get("ingest_stall_detector") is False


def test_168e_kinds_allowlisted(ops_tmp) -> None:
    for kind in (
        "translate_stalled",
        "worker_lost",
        "reclaim_attempt",
        "translate_section_tick",
    ):
        oev.emit(kind, job_id="job_abc123def456", details={"reason": "translate_idle"})
    kinds = {r["kind"] for r in oev.list_events(limit=20)}
    assert "translate_stalled" in kinds
    assert "worker_lost" in kinds
    assert "reclaim_attempt" in kinds


def test_check_translate_stall_idle(ops_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_INGEST_STALL_SEC", "10")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    job = {
        "done": False,
        "error": None,
        "stage": "translate",
        "percent": 92,
        "message": "서론 번역 10/11",
        "_progress_key": "92|x",
        "_progress_ts": (now - timedelta(seconds=30)).isoformat(),
    }
    assert stall.check_translate_stall(job, now=now) == "translate_idle"
    job["_progress_ts"] = now.isoformat()
    assert stall.check_translate_stall(job, now=now) is None
    # Live worker must not be killed for long Gemini batches.
    job["_progress_ts"] = (now - timedelta(seconds=30)).isoformat()
    job["_local_running"] = True
    assert stall.check_translate_stall(job, now=now) is None
    job["_local_running"] = False
    future = (now + timedelta(minutes=2)).isoformat()
    job["lease_until"] = future
    assert stall.check_translate_stall(job, now=now) is None


def test_note_job_progress_only_on_change() -> None:
    job: dict = {}
    stall.note_job_progress(job, percent=90, message="a")
    ts1 = job["_progress_ts"]
    stall.note_job_progress(job, percent=90, message="a")
    assert job["_progress_ts"] == ts1
    stall.note_job_progress(job, percent=91, message="a")
    assert job["_progress_ts"] != ts1


def test_job_is_stuck_lease() -> None:
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    job = {
        "done": False,
        "error": None,
        "stage": "debone",
        "lease_until": past,
        "_local_running": False,
    }
    stuck, reason = ij.job_is_stuck(job)
    assert stuck is True
    assert reason == "lease_expired"


def test_sweep_candidate_local_running() -> None:
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    job = {
        "done": False,
        "lease_until": past,
        "_local_running": True,
    }
    assert stall.sweep_candidate(job) == "none"
    job["_local_running"] = False
    assert stall.sweep_candidate(job) == "reclaim"


def test_fail_job_terminal_and_poll_stall(ops_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_INGEST_STALL_SEC", "5")
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    now = datetime.now(timezone.utc)
    jid = "job_aabbccddeeff"
    app_mod._JOBS[jid] = {
        "percent": 93,
        "stage": "translate",
        "message": "서론 번역 10/11",
        "done": False,
        "error": None,
        "owner_uid": "",
        "content_hash": "a" * 64,
        "_progress_key": "93|x",
        "_progress_ts": (now - timedelta(seconds=60)).isoformat(),
    }
    assert app_mod._maybe_fail_translate_stall(jid, app_mod._JOBS[jid]) is True
    job = app_mod._JOBS[jid]
    assert job.get("done") is True
    assert job.get("error")
    kinds = [r["kind"] for r in oev.list_events(limit=20)]
    assert "translate_stalled" in kinds
    del app_mod._JOBS[jid]


def test_job_set_aborts_after_terminal_fail(monkeypatch) -> None:
    """design/169k K3 — zombie worker cooperative abort."""
    jid = "job_ccddeeff1122"
    app_mod._JOBS[jid] = {
        "percent": 90,
        "stage": "translate",
        "done": True,
        "error": "처리 worker가 응답하지 않습니다. 다시 업로드해 주세요.",
    }
    with pytest.raises(app_mod.IngestCancelled):
        app_mod._job_set(jid, percent=91, stage="translate", message="x")
    del app_mod._JOBS[jid]


def test_fail_job_terminal_emits_job_terminal_checkpoint(ev_tmp, monkeypatch) -> None:
    """design/169k K3 — checkpoint before server_job_terminal_error."""
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    jid = "job_ddeeff112233"
    app_mod._JOBS[jid] = {
        "percent": 90,
        "stage": "translate",
        "done": False,
        "error": None,
        "owner_uid": "u1",
        "trace_id": "tr_test",
    }
    assert app_mod._fail_job_terminal(
        jid,
        "worker lost",
        ops_kind="worker_lost",
        details={"reason": "lease_expired"},
        percent=90,
    )
    cps = [
        r["details"].get("checkpoint")
        for r in eb.list_events(limit=30)
        if r.get("kind") == "checkpoint"
    ]
    assert "job_terminal" in cps
    del app_mod._JOBS[jid]


def test_stuck_admin_403(ops_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    res = TestClient(app).get("/api/ops/ingest/jobs/stuck")
    assert res.status_code == 403


def test_stuck_admin_lists_lease_expired(ops_tmp, monkeypatch) -> None:
    client, token = _admin_client(monkeypatch)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    jid = "job_112233445566"
    app_mod._JOBS[jid] = {
        "percent": 40,
        "stage": "debone",
        "message": "debone",
        "done": False,
        "error": None,
        "lease_until": past,
        "_local_running": False,
        "content_hash": "b" * 64,
    }
    res = client.get("/api/ops/ingest/jobs/stuck", cookies={"asr_session": token})
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    ids = [r["job_id"] for r in body.get("jobs") or []]
    assert jid in ids
    del app_mod._JOBS[jid]


def test_integrity_admin_404(ops_tmp, monkeypatch) -> None:
    client, token = _admin_client(monkeypatch)
    res = client.get(
        "/api/ops/cache/zzzzzzzz/integrity", cookies={"asr_session": token}
    )
    assert res.status_code == 404


def test_integrity_admin_mismatch(ops_tmp, monkeypatch, tmp_path) -> None:
    from sentence_reading.cache import paper_cache as pc

    client, token = _admin_client(monkeypatch)
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    cid = "abcd1234ef"
    paper = tmp_path / cid
    paper.mkdir(parents=True)
    (paper / "session.json").write_text(
        '{"title":"t","sentences":[{"id":"s1","text":"Hello world sentence."}],'
        '"figures":[{"id":"fig-1","caption":"c","file":"figures/fig-1.png"}],'
        '"pipeline_version":"rich-v24"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        pc,
        "get_index_entry",
        lambda _cid: {
            "id": cid,
            "sentence_count": 1,
            "figure_count": 0,
            "ingest_status": "ok",
        },
    )
    res = client.get(
        f"/api/ops/cache/{cid}/integrity", cookies={"asr_session": token}
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    invs = {v.get("invariant") for v in body.get("violations") or []}
    assert "T4" in invs or body.get("violation_count", 0) >= 1


def test_violations_to_public_filters() -> None:
    rows = violations_to_public(
        [
            Violation(
                invariant="T9",
                code="figures_meta_dropped",
                details={"session_n": 12, "meta_n": 0, "bad": "has space"},
            )
        ]
    )
    assert rows[0]["invariant"] == "T9"
    assert rows[0]["details"]["session_n"] == 12
    assert "bad" not in rows[0]["details"]
