"""유저별 사용량 · 추정 비용 (0.2.67 · design/27 · 관리자 전용 UI/API)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import usage_meter as um
from sentence_reading.llm.auth_google import AuthUser


@pytest.fixture(autouse=True)
def _iso_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(um, "project_root", lambda: root)
    monkeypatch.setattr(um, "usage_local_path", lambda uid: root / "data" / "usage" / f"{uid}.json")
    monkeypatch.delenv("ASR_ADMIN_EMAILS", raising=False)
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_version() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.2.67"
    assert st.get("usage_meter") is True


def test_estimate_usd() -> None:
    est = um.estimate_usd(
        {
            "gemini_input_chars": 1_000_000,
            "gemini_output_chars": 1_000_000,
            "tts_chars": 1_000_000,
            "gcs_upload_bytes": 0,
            "gcs_download_bytes": 0,
        }
    )
    assert est["gemini_usd"] == pytest.approx(2.8, rel=1e-6)
    assert est["tts_usd"] == pytest.approx(16.0, rel=1e-6)
    assert est["total_usd"] == pytest.approx(18.8, rel=1e-6)


def test_record_and_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-usage-meter-xxxxxxxx")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    user = AuthUser(
        uid="118234567890123456789",
        email="admin@example.com",
        name="Admin",
        picture="",
    )
    token = ag.issue_session_token(user)
    um.record(
        uid=user.uid,
        email=user.email,
        gemini_calls=2,
        gemini_input_chars=100,
        gemini_output_chars=50,
        tts_cloud_calls=1,
        tts_chars=20,
    )
    client = TestClient(app)
    me = client.get("/api/usage", cookies={ag.COOKIE_NAME: token}).json()
    assert me["ok"] is True
    assert me["totals"]["gemini_calls"] == 2
    assert me["estimate_usd"]["total_usd"] >= 0
    ad = client.get("/api/usage/admin", cookies={ag.COOKIE_NAME: token}).json()
    assert ad["ok"] is True
    assert len(ad["users"]) >= 1


def test_usage_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/usage").json()["error"] == "auth_required"


def test_usage_me_forbidden_for_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-usage-meter-xxxxxxxx")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    user = AuthUser(
        uid="118234567890123456780",
        email="other@example.com",
        name="Other",
        picture="",
    )
    token = ag.issue_session_token(user)
    client = TestClient(app)
    me = client.get("/api/usage", cookies={ag.COOKIE_NAME: token}).json()
    assert me["error"] == "forbidden"


def test_admin_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-usage-meter-xxxxxxxx")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    user = AuthUser(
        uid="118234567890123456780",
        email="other@example.com",
        name="Other",
        picture="",
    )
    token = ag.issue_session_token(user)
    client = TestClient(app)
    ad = client.get("/api/usage/admin", cookies={ag.COOKIE_NAME: token}).json()
    assert ad["error"] == "forbidden"


def test_design_mentions_version() -> None:
    root = Path(__file__).resolve().parents[1]
    design = (root / "docs" / "design" / "27-usage-metering.md").read_text(encoding="utf-8")
    assert "0.2.37" in design
    assert "관리자" in design
