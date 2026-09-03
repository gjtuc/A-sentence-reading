"""Access gate hot-path TTL cache (0.3.153 · design/173a)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sentence_reading.llm import access_gate as ag
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE_TTL_S", "45")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "access-gate-ttl-test-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(ag, "project_root", lambda: root)
    from sentence_reading.cache import paper_cache as pc

    monkeypatch.setattr(pc, "project_root", lambda: root)
    agu.reset_gcs_uid()
    ag.reset_access_gate_cache_for_tests()
    yield
    ag.reset_access_gate_cache_for_tests()
    agu.reset_gcs_uid()


def test_ttl_env_clamp_and_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_ACCESS_GATE_TTL_S", "999")
    assert ag.access_gate_ttl_seconds() == 60
    monkeypatch.setenv("ASR_ACCESS_GATE_TTL_S", "3")
    assert ag.access_gate_ttl_seconds() == 5
    monkeypatch.setenv("ASR_ACCESS_GATE_TTL_S", "0")
    assert ag.access_gate_ttl_seconds() == 0
    monkeypatch.delenv("ASR_ACCESS_GATE_TTL_S", raising=False)
    assert ag.access_gate_ttl_seconds() == 45


def test_ttl_hit_skips_gcs_download(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"pull": 0, "download": 0}

    def _pull() -> bool:
        calls["pull"] += 1
        return False

    def _download(name: str):
        calls["download"] += 1
        return None

    monkeypatch.setattr(aa, "pull_accounts_from_gcs", _pull)
    monkeypatch.setattr(ag, "_download_auth_json", _download)

    ag.refresh_access_gate_from_gcs()
    ag.refresh_access_gate_from_gcs()
    assert calls["pull"] == 1
    assert calls["download"] == 3  # invite, events, redeem once each


def test_force_refresh_bypasses_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"pull": 0}

    monkeypatch.setattr(aa, "pull_accounts_from_gcs", lambda: calls.__setitem__("pull", calls["pull"] + 1) or False)
    monkeypatch.setattr(ag, "_download_auth_json", lambda name: None)

    ag.refresh_access_gate_from_gcs()
    ag.refresh_access_gate_from_gcs(force=True)
    assert calls["pull"] == 2


def test_ttl_zero_always_pulls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_ACCESS_GATE_TTL_S", "0")
    ag.reset_access_gate_cache_for_tests()
    calls = {"pull": 0}
    monkeypatch.setattr(aa, "pull_accounts_from_gcs", lambda: calls.__setitem__("pull", calls["pull"] + 1) or False)
    monkeypatch.setattr(ag, "_download_auth_json", lambda name: None)

    ag.refresh_access_gate_from_gcs()
    ag.refresh_access_gate_from_gcs()
    assert calls["pull"] == 2


def test_write_invalidates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"pull": 0}
    monkeypatch.setattr(aa, "pull_accounts_from_gcs", lambda: calls.__setitem__("pull", calls["pull"] + 1) or False)
    monkeypatch.setattr(ag, "_download_auth_json", lambda name: None)
    monkeypatch.setattr(ag, "_push_auth_json", lambda path, filename: None)

    ag.refresh_access_gate_from_gcs()
    ag._write_invites({"version": 1, "codes": []})
    ag.refresh_access_gate_from_gcs()
    assert calls["pull"] == 2


def test_decide_deny_visible_after_invalidate(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = "u" * 20
    store = {
        "version": 1,
        "users": {
            uid: {
                "uid": uid,
                "email": "u@example.com",
                "access": {"status": "allowed", "decided_at": 1},
            }
        },
        "by_provider": {},
    }
    ag._write_accounts(store)
    ag.reset_access_gate_cache_for_tests()
    monkeypatch.setattr(ag, "_download_auth_json", lambda name: None)
    monkeypatch.setattr(aa, "pull_accounts_from_gcs", lambda: False)

    ag.refresh_access_gate_from_gcs()
    assert ag.user_may_use_paid(uid) is True

    ag.decide_access(uid, "deny", admin_email="admin@example.com")
    assert ag.user_may_use_paid(uid) is False


def test_status_exposes_access_gate_ttl() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.153"
    assert st["access_gate_ttl_s"] == 45
    assert "access_gate_cache" in st
    assert st["access_gate_cache"]["ttl_s"] == 45
