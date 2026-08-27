# -*- coding: utf-8 -*-
"""design/132 — cancel early ingest/upload; refuse late stages; AuthZ."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_chunked as ic

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "132-ingest-cancel.md"
CLIENT = ROOT / "mobile" / "lib" / "api" / "client.dart"
CTRL = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
SCREEN = ROOT / "mobile" / "lib" / "screens" / "library_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
INDEX = ROOT / "src" / "sentence_reading" / "static" / "index.html"


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "ingest-cancel-test-secret")
    monkeypatch.setenv("ASR_CHUNKED_UPLOAD", "1")
    monkeypatch.setenv("ASR_INGEST_CANCEL", "1")
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    agu.reset_gcs_uid()
    ic.clear_memory_for_tests()
    app_mod._JOBS.clear()
    yield
    ic.clear_memory_for_tests()
    app_mod._JOBS.clear()
    agu.reset_gcs_uid()


def _register(client: TestClient, email: str, name: str = "U") -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": name},
    )
    assert r.status_code == 200, r.text


def test_status_flag_and_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.71"
    assert st["ingest_cancel"] is True
    assert st["mobile_ingest_cancel"] is True


def test_kill_switch_disables_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_INGEST_CANCEL", "0")
    st = TestClient(app).get("/api/status").json()
    assert st["ingest_cancel"] is False
    client = TestClient(app)
    _register(client, "kill@example.com")
    r = client.post("/api/ingest/jobs/job_aabbccddeeff/cancel")
    assert r.status_code == 503
    assert r.json()["error"] == "cancel_disabled"


def test_cancel_requires_auth() -> None:
    r = TestClient(app).post("/api/ingest/jobs/job_aabbccddeeff/cancel")
    assert r.status_code == 401


def test_cancel_path_traversal_404() -> None:
    client = TestClient(app)
    _register(client, "path@example.com")
    r = client.post("/api/ingest/jobs/../job_aabbccddeeff/cancel")
    assert r.status_code == 404


def test_cancel_early_discards_job() -> None:
    client = TestClient(app)
    _register(client, "early@example.com")
    me = client.get("/api/auth/status").json()
    uid = me["user"]["uid"]
    jid = "job_aabbccddeeff"
    app_mod._JOBS[jid] = {
        "owner_uid": uid,
        "percent": 12,
        "stage": "quality",
        "message": "품질 검사",
        "done": False,
        "filename": "sample.pdf",
        "_local_running": False,
    }
    r = client.post(f"/api/ingest/jobs/{jid}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["cancelled"] is True
    assert jid not in app_mod._JOBS
    # Poll must not fake-success a wiped job.
    st = client.get(f"/api/ingest/jobs/{jid}")
    assert st.status_code == 404


def test_cancel_too_late_at_ready() -> None:
    client = TestClient(app)
    _register(client, "late@example.com")
    me = client.get("/api/auth/status").json()
    uid = me["user"]["uid"]
    jid = "job_bbccddeeffaa"
    app_mod._JOBS[jid] = {
        "owner_uid": uid,
        "percent": 88,
        "stage": "ready",
        "message": "읽기 시작",
        "done": False,
        "filename": "sample.pdf",
        "result": {"cache_id": "pap_test123456", "ok": True},
        "_local_running": True,
    }
    r = client.post(f"/api/ingest/jobs/{jid}/cancel")
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cancel_too_late"
    # Job must remain for finish path.
    assert jid in app_mod._JOBS
    assert app_mod._JOBS[jid].get("cancel_requested") is not True


def test_cross_user_cancel_is_404() -> None:
    a = TestClient(app)
    b = TestClient(app)
    _register(a, "a@example.com", "A")
    _register(b, "b@example.com", "B")
    uid_a = a.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_ccddeeffaabb"
    app_mod._JOBS[jid] = {
        "owner_uid": uid_a,
        "percent": 20,
        "stage": "vision",
        "message": "비전",
        "done": False,
        "filename": "a.pdf",
        "_local_running": False,
    }
    r = b.post(f"/api/ingest/jobs/{jid}/cancel")
    assert r.status_code == 404
    # Owner job untouched.
    assert jid in app_mod._JOBS
    assert app_mod._JOBS[jid]["owner_uid"] == uid_a


def test_upload_cancel_owner_only() -> None:
    client = TestClient(app)
    _register(client, "upl@example.com")
    me = client.get("/api/auth/status").json()
    uid = me["user"]["uid"]
    meta = ic.create_upload_session(
        owner_uid=uid,
        content_hash="a" * 64,
        filename="x.pdf",
        size=900,
    )
    assert meta is not None
    upl = meta["upload_id"]
    r = client.post(f"/api/ingest/uploads/{upl}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["cancelled"] is True
    assert ic.get_upload(upl, owner_uid=uid) is None


def test_design_and_clients_pin() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.48" in text
    assert "cancel_too_late" in text
    assert "ASR_INGEST_CANCEL" in text
    dart = CLIENT.read_text(encoding="utf-8")
    assert "cancelIngestJob" in dart
    assert "UploadCancelledException" in dart
    assert "design/132" in CTRL.read_text(encoding="utf-8")
    assert "cancelUpload" in CTRL.read_text(encoding="utf-8")
    assert "취소" in SCREEN.read_text(encoding="utf-8")
    assert "0.3.71" in PUB.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    assert "requestIngestCancel" in js
    assert "uploadCancelBtn" in INDEX.read_text(encoding="utf-8")


def test_empty_and_huge_job_id_rejected() -> None:
    client = TestClient(app)
    _register(client, "edge@example.com")
    assert client.post("/api/ingest/jobs//cancel").status_code in (404, 405)
    huge = "job_" + ("a" * 200)
    r = client.post(f"/api/ingest/jobs/{huge}/cancel")
    assert r.status_code == 404
