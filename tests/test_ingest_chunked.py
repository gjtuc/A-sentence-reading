"""Chunked upload + prefix integrity (0.3.3 · design/72)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_chunked as ic


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "chunked-upload-test-secret")
    monkeypatch.setenv("ASR_CHUNKED_UPLOAD", "1")
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    agu.reset_gcs_uid()
    ic.clear_memory_for_tests()
    yield
    ic.clear_memory_for_tests()
    agu.reset_gcs_uid()


def _pdf(n: int = 900) -> bytes:
    # Minimal PDF-like + padding so multi-chunk
    body = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + (b"x" * n)
    return body


def _register(client: TestClient, email: str = "u@example.com") -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": "U"},
    )
    assert r.status_code == 200, r.text


def test_status_flag():
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.44"
    assert st["ingest_chunked_upload"] is True


def test_chunked_upload_resume_and_complete(monkeypatch: pytest.MonkeyPatch):
    # Avoid running full ingest pipeline — stub begin.
    from sentence_reading.api import app as app_mod

    def fake_begin(
        raw,
        filename,
        kind,
        *,
        owner_uid,
        want_shadowing_chunks=False,
        want_translate=True,
    ):
        # design/80·99 — accept opt-in flags; tests ignore them.
        return {
            "ok": True,
            "job_id": "job_aabbccddeeff",
            "percent": 1,
            "message": "업로드 완료, 읽기 시작",
            "content_hash": hashlib.sha256(raw).hexdigest(),
        }

    monkeypatch.setattr(app_mod, "_begin_ingest_from_bytes", fake_begin)

    client = TestClient(app)
    _register(client)
    raw = _pdf(ic.CHUNK_SIZE + 100)
    digest = hashlib.sha256(raw).hexdigest()
    created = client.post(
        "/api/ingest/uploads",
        json={"filename": "a.pdf", "content_hash": digest, "size": len(raw)},
    )
    assert created.status_code == 200, created.text
    upl = created.json()["upload_id"]
    assert upl.startswith("upl_")

    # First chunk
    c0 = raw[: ic.CHUNK_SIZE]
    r0 = client.put(
        f"/api/ingest/uploads/{upl}?offset=0",
        content=c0,
        headers={"X-Chunk-Sha256": hashlib.sha256(c0).hexdigest()},
    )
    assert r0.status_code == 200, r0.text
    assert r0.json()["received_offset"] == ic.CHUNK_SIZE
    prefix = r0.json()["prefix_sha256"]
    assert prefix == hashlib.sha256(c0).hexdigest()

    # Integrity probe
    st = client.get(f"/api/ingest/uploads/{upl}").json()
    assert st["received_offset"] == ic.CHUNK_SIZE
    assert st["prefix_sha256"] == prefix

    # Wrong offset rejected
    bad = client.put(
        f"/api/ingest/uploads/{upl}?offset=0",
        content=c0,
        headers={"X-Chunk-Sha256": hashlib.sha256(c0).hexdigest()},
    )
    assert bad.status_code == 409

    # Second (last) chunk
    c1 = raw[ic.CHUNK_SIZE :]
    r1 = client.put(
        f"/api/ingest/uploads/{upl}?offset={ic.CHUNK_SIZE}",
        content=c1,
        headers={"X-Chunk-Sha256": hashlib.sha256(c1).hexdigest()},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["received_offset"] == len(raw)

    done = client.post(f"/api/ingest/uploads/{upl}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["job_id"] == "job_aabbccddeeff"
    assert done.json()["content_hash"] == digest


def test_cross_user_upload_hidden():
    a = TestClient(app)
    _register(a, "a@example.com")
    raw = _pdf(50)
    digest = hashlib.sha256(raw).hexdigest()
    upl = a.post(
        "/api/ingest/uploads",
        json={"filename": "a.pdf", "content_hash": digest, "size": len(raw)},
    ).json()["upload_id"]

    b = TestClient(app)
    _register(b, "b@example.com")
    r = b.get(f"/api/ingest/uploads/{upl}")
    assert r.status_code == 404


def test_chunk_hash_mismatch():
    client = TestClient(app)
    _register(client)
    raw = _pdf(50)
    digest = hashlib.sha256(raw).hexdigest()
    upl = client.post(
        "/api/ingest/uploads",
        json={"filename": "a.pdf", "content_hash": digest, "size": len(raw)},
    ).json()["upload_id"]
    r = client.put(
        f"/api/ingest/uploads/{upl}?offset=0",
        content=raw,
        headers={"X-Chunk-Sha256": "ab" * 32},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "chunk_hash_mismatch"


def test_kill_switch_rejects_create(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_CHUNKED_UPLOAD", "0")
    client = TestClient(app)
    _register(client)
    raw = _pdf(50)
    r = client.post(
        "/api/ingest/uploads",
        json={
            "filename": "a.pdf",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        },
    )
    assert r.status_code == 503
    assert r.json()["error"] == "chunked_upload_disabled"


def test_unauth_create_rejected():
    client = TestClient(app)
    raw = _pdf(50)
    r = client.post(
        "/api/ingest/uploads",
        json={
            "filename": "a.pdf",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        },
    )
    assert r.status_code == 401


def test_bad_size_rejected():
    client = TestClient(app)
    _register(client)
    r = client.post(
        "/api/ingest/uploads",
        json={
            "filename": "a.pdf",
            "content_hash": "ab" * 32,
            "size": -1,
        },
    )
    assert r.status_code == 400


def test_design_72():
    p = Path("docs/design/72-chunked-upload.md")
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.2.89" in text
    assert "prefix_sha256" in text
    assert "ingest_chunked_upload" in text
    assert "ASR_CHUNKED_UPLOAD" in text
