# -*- coding: utf-8 -*-
"""design/107 — ingest job reclaim across Cloud Run instances."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_jobs_gcs as ij

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "107-ingest-job-reclaim.md"


@pytest.fixture()
def fake_gcs(monkeypatch: pytest.MonkeyPatch):
    bucket: dict[str, bytes] = {}

    def upload(name: str, data: bytes, *, content_type: str = "", meter: bool = True) -> bool:
        bucket[name] = bytes(data)
        return True

    def download(name: str, *, meter: bool = True) -> bytes | None:
        return bucket.get(name)

    def delete(name: str) -> bool:
        return bucket.pop(name, None) is not None

    monkeypatch.setenv("ASR_GCS_BUCKET", "fake-bucket")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "reclaim-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_INGEST_JOB_RECLAIM", "1")
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.upload_bytes", upload)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.download_bytes", download)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.delete_bytes", delete)
    monkeypatch.setattr(ij, "upload_bytes", upload)
    monkeypatch.setattr(ij, "download_bytes", download)
    monkeypatch.setattr(ij, "delete_bytes", delete)
    agu.reset_gcs_uid()
    yield bucket
    agu.reset_gcs_uid()
    app_mod._JOBS.clear()


@pytest.fixture()
def auth_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    return root


def _register(client: TestClient, email: str) -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": "T"},
    )
    assert r.status_code == 200, r.text


def test_status_reclaim_flag(fake_gcs, auth_root):
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.40"
    assert st["ingest_job_reclaim"] is True


def test_design_107_exists():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.21" in text
    assert "lease" in text.lower()
    assert "ASR_INGEST_JOB_RECLAIM" in text


def test_lease_expired_helper():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert ij.lease_expired({}, now=now) is True
    future = (now + timedelta(seconds=60)).isoformat()
    assert ij.lease_expired({"lease_until": future}, now=now) is False
    past = (now - timedelta(seconds=1)).isoformat()
    assert ij.lease_expired({"lease_until": past}, now=now) is True


def test_try_claim_lease_and_load_upload(fake_gcs, auth_root):
    client = TestClient(app)
    _register(client, "owner@example.com")
    uid = client.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_aabbccddeeff"
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    job = {
        "percent": 12,
        "stage": "quality",
        "message": "추출 품질 보는 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid,
        "content_hash": "a" * 64,
        "filename": "paper.pdf",
        "lease_until": past,
        "lease_token": "oldtoken",
    }
    assert ij.save_ingest_job(jid, job) is True
    assert ij.save_ingest_upload(jid, b"%PDF-1.4 reclaim-bytes", owner_uid=uid) is True
    tok = ij.try_claim_lease(jid, owner_uid=uid)
    assert tok is not None
    loaded = ij.load_ingest_job(jid, owner_uid=uid)
    assert loaded is not None
    assert loaded["lease_token"] == tok
    assert ij.lease_expired(loaded) is False
    raw = ij.load_ingest_upload(jid, owner_uid=uid)
    assert raw == b"%PDF-1.4 reclaim-bytes"


def test_active_lease_not_claimed(fake_gcs, auth_root):
    client = TestClient(app)
    _register(client, "alive@example.com")
    uid = client.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_112233445566"
    future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    job = {
        "percent": 12,
        "stage": "quality",
        "message": "추출 품질 보는 중",
        "done": False,
        "owner_uid": uid,
        "content_hash": "b" * 64,
        "filename": "x.pdf",
        "lease_until": future,
        "lease_token": "alive",
    }
    assert ij.save_ingest_job(jid, job) is True
    assert ij.try_claim_lease(jid, owner_uid=uid) is None


def test_cross_user_cannot_reclaim(fake_gcs, auth_root):
    a = TestClient(app)
    _register(a, "a@example.com")
    uid_a = a.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_deadbeef0001"
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    job = {
        "percent": 12,
        "stage": "quality",
        "message": "추출 품질 보는 중",
        "done": False,
        "owner_uid": uid_a,
        "content_hash": "c" * 64,
        "filename": "a.pdf",
        "lease_until": past,
    }
    assert ij.save_ingest_job(jid, job) is True
    assert ij.save_ingest_upload(jid, b"%PDF-1.4 a", owner_uid=uid_a) is True

    b = TestClient(app)
    _register(b, "b@example.com")
    st = b.get(f"/api/ingest/jobs/{jid}")
    assert st.status_code == 404
    # B must not be able to claim A's lease either.
    uid_b = b.get("/api/auth/status").json()["user"]["uid"]
    assert ij.try_claim_lease(jid, owner_uid=uid_b) is None


def test_poll_reclaims_stale_job(fake_gcs, auth_root, monkeypatch: pytest.MonkeyPatch):
    """Owner poll on empty memory + expired lease starts a local worker."""
    client = TestClient(app)
    _register(client, "reclaim@example.com")
    uid = client.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_abc123def456"
    past = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
    job = {
        "percent": 12,
        "stage": "quality",
        "message": "추출 품질 보는 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid,
        "content_hash": "d" * 64,
        "filename": "stale.pdf",
        "lease_until": past,
        "want_translate": False,
    }
    assert ij.save_ingest_job(jid, job) is True
    # Minimal PDF bytes — reclaim will run extract; may error, but must start worker.
    assert ij.save_ingest_upload(jid, b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n", owner_uid=uid)

    started: list[str] = []

    async def fake_run(job_id, tmp_path, filename, kind, **kwargs):
        started.append(job_id)
        j = app_mod._JOBS.get(job_id)
        if j is not None:
            j["done"] = True
            j["percent"] = 100
            j["message"] = "reclaimed-fake"
            j["_local_running"] = False
            j["result"] = {
                "ok": True,
                "cache_id": "cache_test",
                "session_id": "ses_test",
            }

    monkeypatch.setattr(app_mod, "_run_ingest_job", fake_run)

    # Simulate other instance: no local memory.
    app_mod._JOBS.clear()
    st = client.get(f"/api/ingest/jobs/{jid}")
    assert st.status_code == 200, st.text
    body = st.json()
    assert started == [jid]
    assert "처리 다시 시작" in body.get("message", "") or body.get("done") is True
    assert jid in app_mod._JOBS


def test_kill_switch_disables_status_flag(fake_gcs, auth_root, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_INGEST_JOB_RECLAIM", "0")
    st = TestClient(app).get("/api/status").json()
    assert st["ingest_job_reclaim"] is False
