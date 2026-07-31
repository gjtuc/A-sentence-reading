"""voice blob GCS path · limits · API."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import voice_gcs as vg


def test_voice_object_is_sha_of_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    key = "cache:abc|s1|123"
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert vg.voice_blob_digest(key) == digest
    assert vg.voice_blob_object(key) == f"asr/voice/{digest}.bin"


def test_voice_key_edge_cases() -> None:
    assert vg.voice_blob_object("") is None
    assert vg.voice_blob_object("x" * (vg.VOICE_BLOB_KEY_MAX + 1)) is None
    assert vg.upload_voice_blob("k", b"") is False
    assert vg.upload_voice_blob("k", b"x" * (vg.VOICE_BLOB_MAX_BYTES + 1)) is False


def test_upload_download_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    store: dict[str, bytes] = {}

    def fake_upload(name, data, content_type="application/octet-stream"):
        store[name] = data
        return True

    def fake_download(name):
        return store.get(name)

    monkeypatch.setattr(vg, "upload_bytes", fake_upload)
    monkeypatch.setattr(vg, "download_bytes", fake_download)
    key = "ses:1|sent|99"
    assert vg.upload_voice_blob(key, b"webm-bytes", content_type="audio/webm") is True
    assert vg.download_voice_blob(key) == b"webm-bytes"
    assert vg.download_voice_blob("missing|key|0") is None


def test_api_voice_unavailable() -> None:
    client = TestClient(app)
    r = client.get("/api/voice/blobs", params={"key": "a|b|1"})
    # no bucket → 503
    assert r.status_code in (503, 404)
    st = client.get("/api/status").json()
    assert st["version"] == "0.2.82"
    assert st["gcs"]["voice_blob_sync"] is True
    assert st["gcs"]["papers_sync"] is True


def test_api_voice_put_get_with_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    cred = tmp_path / "sa.json"
    cred.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred))

    mem: dict[str, bytes] = {}

    def fake_up(key, data, content_type="application/octet-stream"):
        mem[key] = bytes(data)
        return True

    def fake_down(key):
        return mem.get(key)

    monkeypatch.setattr(
        "sentence_reading.api.app.gcs_status",
        lambda: {
            "enabled": True,
            "ready": True,
            "message": "ok",
        },
    )
    monkeypatch.setattr("sentence_reading.api.app.upload_voice_blob", fake_up)
    monkeypatch.setattr("sentence_reading.api.app.download_voice_blob", fake_down)

    client = TestClient(app)
    key = "cache:p|s|1"
    put = client.put(
        "/api/voice/blobs",
        params={"key": key},
        content=b"AUDIO",
        headers={"content-type": "audio/webm"},
    )
    assert put.status_code == 200
    assert put.json()["uploaded"] is True
    got = client.get("/api/voice/blobs", params={"key": key})
    assert got.status_code == 200
    assert got.content == b"AUDIO"


def test_api_rejects_bad_key_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.api.app.gcs_status",
        lambda: {"enabled": True, "ready": True, "message": "ok"},
    )
    client = TestClient(app)
    assert client.put("/api/voice/blobs", params={"key": ""}, content=b"x").status_code == 400
    assert (
        client.put("/api/voice/blobs", params={"key": "ok"}, content=b"").status_code == 400
    )
    assert client.get("/api/voice/blobs", params={"key": ""}).status_code == 400


def test_client_wiring() -> None:
    app_js = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")
    assert "fetchVoiceBlobFromCloud" in app_js
    assert "uploadVoiceBlobToCloud" in app_js
    assert "/api/voice/blobs" in app_js


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
