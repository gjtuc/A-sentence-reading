"""Google 로그인 · UID별 GCS 경로 계약 (0.2.18 경로 · 0.2.24 버전)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import gcs_sync as gs
from sentence_reading.llm import notes_gcs as ng
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.llm.auth_google import AuthUser


@pytest.fixture(autouse=True)
def _clear_uid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # WHY: 이메일 기본 on — Google-only 계약 테스트는 email off
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.delenv("ASR_KAKAO_REST_API_KEY", raising=False)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_version_and_auth_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.2.38"
    assert "auth" in st
    assert st["auth"]["auth_enabled"] is False


def test_sanitize_uid() -> None:
    assert ag.sanitize_uid("118234567890123456789") == "118234567890123456789"
    assert ag.sanitize_uid("../x") is None
    assert ag.sanitize_uid("ab") is None
    assert ag.sanitize_uid("") is None


def test_personal_object_legacy_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    ag.reset_gcs_uid()
    assert gs.personal_object_name("notes", "store_v2.json") == "asr/notes/store_v2.json"
    assert ng.notes_store_object() == "asr/notes/store_v2.json"


def test_personal_object_with_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    ag.set_gcs_uid("118234567890123456789")
    assert (
        gs.personal_object_name("notes", "store_v2.json")
        == "asr/users/118234567890123456789/notes/store_v2.json"
    )
    assert (
        pg.papers_index_object()
        == "asr/users/118234567890123456789/papers/index.json"
    )
    # TTS 는 공유
    assert gs.tts_cache_object("abc123") == "asr/tts_cache/abc123.mp3"


def test_personal_object_auth_on_without_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    ag.reset_gcs_uid()
    assert gs.personal_object_name("notes", "store_v2.json") is None


def test_session_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-for-auth")
    user = AuthUser(uid="118234567890123456789", email="a@b.com", name="A")
    tok = ag.issue_session_token(user)
    back = ag.parse_session_token(tok)
    assert back is not None
    assert back.uid == user.uid
    assert back.email == "a@b.com"
    assert ag.parse_session_token("garbage") is None


def test_login_sets_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-for-auth")

    def fake_verify(cred: str) -> AuthUser:
        assert cred == "fake-jwt"
        return AuthUser(uid="118234567890123456789", email="u@example.com", name="U")

    monkeypatch.setattr(ag, "verify_google_id_token", fake_verify)
    monkeypatch.setattr(
        "sentence_reading.api.app.verify_google_id_token", fake_verify
    )
    client = TestClient(app)
    res = client.post("/api/auth/google", json={"credential": "fake-jwt"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["user"]["uid"] == "118234567890123456789"
    assert ag.COOKIE_NAME in res.cookies

    st = client.get("/api/auth/status")
    assert st.json()["user"]["email"] == "u@example.com"
    # middleware sets uid → notes path scoped
    notes = client.get("/api/status").json()["gcs"]["notes_object"]
    assert notes == "asr/users/118234567890123456789/notes/store_v2.json"


def test_notes_sync_needs_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    client = TestClient(app)
    res = client.get("/api/notes/sync")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body.get("needs_auth") is True


def test_ui_auth_wiring() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
    )
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "authLoginBtn" in html
    assert "꺼내보세요" in html
    app_js = (root / "app.js").read_text(encoding="utf-8")
    assert "initAuth" in app_js
    assert "/api/auth/google" in app_js
    notes = (root / "notes_revisions.js").read_text(encoding="utf-8")
    assert "setAccountScope" in notes
    assert ".u." in notes


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
