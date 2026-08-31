"""Server-only upload audit log (ingest trail)."""

from __future__ import annotations

import json

import pytest

from sentence_reading.llm import upload_audit_log as ual


@pytest.fixture(autouse=True)
def _audit_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_UPLOAD_AUDIT_LOG", "1")
    monkeypatch.setattr(ual, "local_events_path", lambda: tmp_path / "events.jsonl")
    monkeypatch.setattr(ual, "_gcs_events_object", lambda: None)


def test_record_upload_persists_uid_cache_filename(monkeypatch, tmp_path):
    monkeypatch.delenv("ASR_UPLOAD_AUDIT_LOG", raising=False)
    monkeypatch.setenv("ASR_UPLOAD_AUDIT_LOG", "1")
    ev = ual.record_upload(
        uid="user_abc123",
        cache_id="cache_feNi01",
        filename="../../secret/paper FeNi dry.pdf",
        job_id="job_abc123def456",
    )
    assert ev is not None
    assert ev["uid"] == "user_abc123"
    assert ev["cache_id"] == "cache_feNi01"
    assert ev["filename"] == "paper FeNi dry.pdf"
    assert ev["job_id"] == "job_abc123def456"
    assert "title" not in ev
    assert "email" not in ev
    raw = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    row = json.loads(raw.strip().splitlines()[-1])
    assert row["cache_id"] == "cache_feNi01"


def test_record_upload_rejects_invalid_cache_id():
    assert (
        ual.record_upload(
            uid="user_ok",
            cache_id="../evil",
            filename="a.pdf",
        )
        is None
    )


def test_kill_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("ASR_UPLOAD_AUDIT_LOG", "0")
    assert ual.upload_audit_enabled() is False
    assert (
        ual.record_upload(
            uid="user_ok",
            cache_id="cache_ok",
            filename="a.pdf",
        )
        is None
    )
    assert not (tmp_path / "events.jsonl").exists()


def test_status_flag():
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st.get("upload_audit_log") is True
