"""Ingest/upload call-count rate limits (0.3.3 · design/73)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_rate_limit as irl


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "ingest-rate-test-secret")
    monkeypatch.setenv("ASR_INGEST_RATE_LIMIT", "1")
    monkeypatch.setenv("ASR_UPLOAD_CREATE_MAX", "3")
    monkeypatch.setenv("ASR_UPLOAD_CREATE_WINDOW_SEC", "600")
    monkeypatch.setenv("ASR_UPLOAD_PUT_MAX", "5")
    monkeypatch.setenv("ASR_UPLOAD_PUT_WINDOW_SEC", "600")
    monkeypatch.setenv("ASR_INGEST_START_MAX", "2")
    monkeypatch.setenv("ASR_INGEST_START_WINDOW_SEC", "600")
    monkeypatch.setenv("ASR_CHUNKED_UPLOAD", "1")
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(irl, "project_root", lambda: root)
    monkeypatch.setattr(irl, "store_path", lambda: root / "data" / "auth" / "ingest_rate.json")
    # Avoid GCS side effects in unit tests
    monkeypatch.setattr(irl, "_push_store", lambda path: None)
    monkeypatch.setattr(irl, "_pull_remote", lambda: None)
    agu.reset_gcs_uid()
    irl.clear_memory_for_tests()
    yield
    irl.clear_memory_for_tests()
    agu.reset_gcs_uid()


def _pdf(n: int = 40) -> bytes:
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + (b"x" * n)


def _register(client: TestClient, email: str) -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": "U"},
    )
    assert r.status_code == 200, r.text


def _create(client: TestClient, raw: bytes):
    return client.post(
        "/api/ingest/uploads",
        json={
            "filename": "a.pdf",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        },
    )


def test_status_flag():
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.17"
    assert st["ingest_rate_limit"] is True


def test_upload_create_rate_limited():
    client = TestClient(app)
    _register(client, "a@example.com")
    raw = _pdf()
    assert _create(client, raw).status_code == 200
    assert _create(client, raw).status_code == 200
    assert _create(client, raw).status_code == 200
    blocked = _create(client, raw)
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"] == "rate_limited"
    assert body["message"] == "요청이 너무 많습니다."
    assert body.get("ok") is False


def test_user_b_not_blocked_when_a_limited():
    a = TestClient(app)
    _register(a, "a@example.com")
    raw = _pdf()
    for _ in range(3):
        assert _create(a, raw).status_code == 200
    assert _create(a, raw).status_code == 429

    b = TestClient(app)
    _register(b, "b@example.com")
    ok = _create(b, raw)
    assert ok.status_code == 200, ok.text


def test_kill_switch_disables_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_INGEST_RATE_LIMIT", "0")
    client = TestClient(app)
    _register(client, "k@example.com")
    raw = _pdf()
    for _ in range(6):
        assert _create(client, raw).status_code == 200
    st = client.get("/api/status").json()
    assert st["ingest_rate_limit"] is False


def test_unauth_create_still_401_with_gate_off_auth_on():
    # Email auth on → create without cookie should 401 before/around rate path.
    client = TestClient(app)
    raw = _pdf()
    r = _create(client, raw)
    assert r.status_code == 401


def test_negative_env_falls_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_UPLOAD_CREATE_MAX", "-9")
    mx, win = irl.limits_for("upload_create")
    assert mx == 12  # module default when invalid
    assert win > 0


def test_design_73():
    p = Path("docs/design/73-ingest-rate-limit.md")
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.3" in text
    assert "요청이 너무 많습니다" in text
    assert "daily" in text.lower() or "하루" in text
    assert "ASR_INGEST_RATE_LIMIT" in text
    assert "용량" in text or "size" in text.lower()
