# -*- coding: utf-8 -*-
"""design/168a — ops_events module + ingest server hooks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import ops_events as oev
from sentence_reading.llm import ingest_jobs_gcs as ij

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "168-ingest-observability.md"


@pytest.fixture()
def ops_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_OPS_EVENTS", "1")
    monkeypatch.setattr(oev, "local_events_path", lambda: tmp_path / "ops_events.jsonl")
    monkeypatch.setattr(oev, "_gcs_events_object", lambda: None)
    return tmp_path


def test_design_doc_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "ops_events" in text
    assert "168a" in text


def test_kill_switch(ops_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_OPS_EVENTS", "0")
    assert oev.ops_events_enabled() is False
    oev.emit("ingest_started", job_id="job_abc123def456")
    assert not oev.local_events_path().is_file()


def test_redact_in_message() -> None:
    ev = oev.build_event(
        "ingest_started",
        job_id="job_abc123def456",
        message="Authorization: Bearer secret-token",
    )
    assert ev is not None
    assert "secret-token" not in ev["message"]
    assert "REDACTED" in ev["message"]


def test_emit_round_trip(ops_tmp) -> None:
    oev.emit(
        "ingest_started",
        trace_id=oev.new_trace_id(),
        job_id="job_abc123def456",
        owner_uid="user123",
        content_hash="a" * 64,
        details={"bytes": 1024, "filename_len": 12},
    )
    rows = oev.list_events(limit=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "ingest_started"
    assert row["job_id"] == "job_abc123def456"
    assert row["details"]["bytes"] == 1024


def test_status_ops_events_pin(ops_tmp) -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.117"
    assert st.get("ops_events") is True
    assert st.get("silent_catch_report") is True
    assert st.get("ingest_stall_detector") is True


def test_status_ops_events_kill(monkeypatch) -> None:
    monkeypatch.setenv("ASR_OPS_EVENTS", "0")
    st = TestClient(app).get("/api/status").json()
    assert st.get("ops_events") is False


def test_push_job_reason_throttle() -> None:
    job = {
        "percent": 5,
        "stage": "extract",
        "_gcs_pushed_percent": 5,
        "_gcs_pushed_stage": "extract",
        "done": False,
        "error": None,
    }
    assert ij.push_job_reason(job) == "throttle"
    assert ij.should_push_job(job) is False


def test_push_job_reason_stage_change() -> None:
    job = {
        "percent": 5,
        "stage": "quality",
        "_gcs_pushed_percent": 5,
        "_gcs_pushed_stage": "extract",
        "done": False,
        "error": None,
    }
    assert ij.push_job_reason(job) == "stage_change"
    assert ij.should_push_job(job) is True


def test_ingest_started_hook(ops_tmp, monkeypatch) -> None:
    monkeypatch.setattr(app_mod, "_JOBS", {})

    def _discard_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(app_mod.asyncio, "create_task", _discard_task)
    monkeypatch.setattr(ij, "save_ingest_upload", lambda *a, **k: True)
    monkeypatch.setattr(ij, "save_ingest_job", lambda *a, **k: True)
    monkeypatch.setattr(ij, "ingest_jobs_gcs_enabled", lambda: False)

    pdf = b"%PDF-1.4 minimal\n"
    out = app_mod._begin_ingest_from_bytes(
        pdf,
        "paper.pdf",
        "pdf",
        owner_uid="uid_test_1",
    )
    assert out["ok"] is True
    kinds = [r["kind"] for r in oev.list_events(limit=20)]
    assert "ingest_started" in kinds


def test_phase_transition_only_on_stage_change(ops_tmp, monkeypatch) -> None:
    monkeypatch.setattr(app_mod, "_JOBS", {})
    monkeypatch.setattr(ij, "save_ingest_job", lambda *a, **k: True)
    monkeypatch.setattr(ij, "ingest_jobs_gcs_enabled", lambda: False)
    monkeypatch.setattr(ij, "stamp_checkpoint_on_job", lambda *a, **k: None)

    job_id = "job_abc123def456"
    app_mod._JOBS[job_id] = {
        "percent": 10,
        "stage": "extract",
        "message": "extracting",
        "done": False,
        "owner_uid": "uid_test_1",
        "content_hash": "b" * 64,
        "trace_id": oev.new_trace_id(),
        "_gcs_pushed_percent": 10,
        "_gcs_pushed_stage": "extract",
    }
    app_mod._job_set(job_id, percent=11, stage="extract", message="still")
    kinds = [r["kind"] for r in oev.list_events(limit=20)]
    assert "ingest_phase_transition" not in kinds

    app_mod._job_set(job_id, percent=12, stage="quality", message="quality")
    kinds = [r["kind"] for r in oev.list_events(limit=20)]
    assert kinds.count("ingest_phase_transition") == 1


def test_persist_job_gcs_skip(ops_tmp, monkeypatch) -> None:
    monkeypatch.setattr(ij, "save_ingest_job", lambda *a, **k: True)
    job_id = "job_abc123def456"
    job = {
        "percent": 5,
        "stage": "extract",
        "_gcs_pushed_percent": 5,
        "_gcs_pushed_stage": "extract",
        "done": False,
        "owner_uid": "uid_test_1",
        "trace_id": oev.new_trace_id(),
        "content_hash": "c" * 64,
    }
    app_mod._persist_job(job_id, job)
    rows = oev.list_events(limit=10)
    skip = [r for r in rows if r["kind"] == "ingest_gcs_skip"]
    assert len(skip) == 1
    assert skip[0]["details"]["reason"] == "throttle"
    push = [r for r in rows if r["kind"] == "ingest_gcs_push"]
    assert not push


def test_persist_job_gcs_push(ops_tmp, monkeypatch) -> None:
    monkeypatch.setattr(ij, "save_ingest_job", lambda *a, **k: True)
    job_id = "job_abc123def456"
    job = {
        "percent": 6,
        "stage": "extract",
        "_gcs_pushed_percent": 5,
        "_gcs_pushed_stage": "extract",
        "done": False,
        "owner_uid": "uid_test_1",
        "trace_id": oev.new_trace_id(),
        "content_hash": "d" * 64,
    }
    app_mod._persist_job(job_id, job)
    rows = oev.list_events(limit=10)
    push = [r for r in rows if r["kind"] == "ingest_gcs_push"]
    assert len(push) == 1
    assert push[0]["details"]["ok"] is True
    assert push[0]["details"]["reason"] == "percent_delta"
