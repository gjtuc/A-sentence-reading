"""Ingest job GCS durability + owner isolation (0.2.95 · design/71)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_jobs_gcs as ij


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
    monkeypatch.setenv("ASR_AUTH_SECRET", "ingest-job-gcs-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.upload_bytes", upload)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.download_bytes", download)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.delete_bytes", delete)
    # ingest_jobs_gcs imports upload_bytes by name — patch module attrs too.
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


def test_status_flags(fake_gcs, auth_root):
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.95"
    assert st["ingest_job_gcs"] is True
    assert st["mobile_upload_resume"] is True


def test_job_survives_memory_clear(fake_gcs, auth_root):
    client = TestClient(app)
    _register(client, "owner@example.com")
    me = client.get("/api/auth/status").json()
    uid = me["user"]["uid"]

    jid = "job_abcd1234ef01"
    app_mod._JOBS[jid] = {
        "percent": 40,
        "stage": "translate",
        "message": "번역 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid,
        "content_hash": "a" * 64,
        "filename": "x.pdf",
    }
    assert ij.save_ingest_job(jid, app_mod._JOBS[jid]) is True
    obj = f"asr/users/{uid}/ingest_jobs/{jid}.json"
    assert obj in fake_gcs
    # Simulate other Cloud Run instance: empty memory.
    del app_mod._JOBS[jid]

    st = client.get(f"/api/ingest/jobs/{jid}")
    assert st.status_code == 200, st.text
    body = st.json()
    assert body["ok"] is True
    assert body["percent"] == 40
    assert body["stage"] == "translate"
    assert body["done"] is False
    # Warm cache
    assert jid in app_mod._JOBS


def test_cross_user_job_hidden(fake_gcs, auth_root):
    client_a = TestClient(app)
    _register(client_a, "a@example.com")
    uid_a = client_a.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_bbbbbbbbbbbb"
    app_mod._JOBS[jid] = {
        "percent": 10,
        "stage": "extract",
        "message": "읽는 중",
        "done": False,
        "owner_uid": uid_a,
        "content_hash": "b" * 64,
        "filename": "a.pdf",
    }
    assert ij.save_ingest_job(jid, app_mod._JOBS[jid])
    del app_mod._JOBS[jid]

    client_b = TestClient(app)
    _register(client_b, "b@example.com")
    # EDGE: B must not see A's durable job (404, not 403 with details).
    r = client_b.get(f"/api/ingest/jobs/{jid}")
    assert r.status_code == 404
    assert r.json()["error"] == "job_not_found"


def test_owner_required_when_set(fake_gcs, auth_root):
    jid = "job_cccccccccccc"
    app_mod._JOBS[jid] = {
        "percent": 5,
        "stage": "queued",
        "message": "x",
        "done": False,
        "owner_uid": "uid_someone_else",
    }
    anon = TestClient(app).get(f"/api/ingest/jobs/{jid}")
    assert anon.status_code == 401


def test_legacy_job_without_owner_still_readable(fake_gcs):
    """Unit contract from design/45 progressive test — no owner_uid."""
    jid = "job_test_partial"
    app_mod._JOBS[jid] = {
        "percent": 10,
        "stage": "extract",
        "message": "",
        "done": False,
        "result": {
            "ok": True,
            "session_id": "ses_x",
            "title": "T",
            "translate_pending": True,
        },
    }
    st = TestClient(app).get(f"/api/ingest/jobs/{jid}").json()
    assert st["session_id"] == "ses_x"
    del app_mod._JOBS[jid]


def test_path_traversal_rejected(fake_gcs):
    r = TestClient(app).get("/api/ingest/jobs/../secrets")
    assert r.status_code == 404


def test_design_doc_mentions_resume():
    design = Path("docs/design/71-mobile-upload-resume.md")
    assert design.is_file()
    text = design.read_text(encoding="utf-8")
    assert "0.2.95" in text
    assert "ingest_job_gcs" in text
    assert "이어올리" in text or "resume" in text.lower()
