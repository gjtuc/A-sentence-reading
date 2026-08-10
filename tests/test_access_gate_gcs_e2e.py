"""Two-identity gate flow with shared fake GCS (0.2.89 · design/69).

Simulates Cloud Run instance A mint → instance B redeem → A allow → B paid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import access_gate as ag
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu


@pytest.fixture()
def shared_gcs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """In-memory GCS shared by two project roots (two 'instances')."""
    bucket: dict[str, bytes] = {}

    def download(name: str) -> dict | None:
        # map filename → object
        key = {
            "invite_codes.json": "asr/auth/invite_codes.json",
            "access_events.json": "asr/auth/access_events.json",
            "redeem_attempts.json": "asr/auth/redeem_attempts.json",
        }.get(name)
        if not key or key not in bucket:
            return None
        return json.loads(bucket[key].decode("utf-8"))

    def push(path: Path, filename: str) -> None:
        key = f"asr/auth/{filename}"
        if path.is_file():
            bucket[key] = path.read_bytes()

    def pull_accounts() -> bool:
        key = "asr/auth/accounts.json"
        if key not in bucket:
            return False
        path = aa.accounts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bucket[key])
        return True

    def write_accounts(store: dict) -> None:
        path = aa.accounts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(store, ensure_ascii=False, indent=2) + "\n"
        path.write_text(raw, encoding="utf-8")
        bucket["asr/auth/accounts.json"] = raw.encode("utf-8")

    monkeypatch.setattr(ag, "_download_auth_json", download)
    monkeypatch.setattr(ag, "_push_auth_json", push)
    monkeypatch.setattr(aa, "pull_accounts_from_gcs", pull_accounts)
    monkeypatch.setattr(ag, "_write_accounts", write_accounts)
    return bucket


def _bind_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(ag, "project_root", lambda: root)
    from sentence_reading.cache import paper_cache as pc

    monkeypatch.setattr(pc, "project_root", lambda: root)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_ACCESS_GATE", "1")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "access-gate-gcs-e2e-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_GCS_BUCKET", "fake-bucket")
    agu.reset_gcs_uid()
    yield
    agu.reset_gcs_uid()


def test_two_instance_mint_redeem_allow(shared_gcs, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root_a = tmp_path / "inst_a"
    root_b = tmp_path / "inst_b"

    # --- Instance A: admin mints ---
    _bind_root(monkeypatch, root_a)
    client_a = TestClient(app)
    r = client_a.post(
        "/api/auth/email/register",
        json={"email": "admin@example.com", "password": "password1", "name": "Ad"},
    )
    assert r.status_code == 200, r.text
    minted = client_a.post("/api/access/admin/mint", json={})
    assert minted.status_code == 200, minted.text
    code = minted.json()["code"]
    assert len(code.replace("-", "")) == 8
    assert "asr/auth/invite_codes.json" in shared_gcs
    inv_raw = shared_gcs["asr/auth/invite_codes.json"].decode("utf-8")
    assert code not in inv_raw  # plaintext OTP must not land in GCS
    assert "hash" in inv_raw

    # --- Instance B: user redeems (empty local invites until refresh) ---
    _bind_root(monkeypatch, root_b)
    client_b = TestClient(app)
    r = client_b.post(
        "/api/auth/email/register",
        json={"email": "user@example.com", "password": "password1", "name": "U"},
    )
    assert r.status_code == 200, r.text
    # paid blocked
    st = client_b.get("/api/access/status").json()
    assert st.get("can_use_paid") is False
    red = client_b.post("/api/access/invite", json={"code": code})
    assert red.status_code == 200, red.text
    assert red.json()["access"]["status"] == "pending"
    assert red.json()["access"]["can_use_paid"] is False

    # --- Instance A: admin allows ---
    _bind_root(monkeypatch, root_a)
    pending = client_a.get("/api/access/admin/pending")
    assert pending.status_code == 200, pending.text
    rows = pending.json().get("pending") or []
    assert rows, pending.text
    uid = rows[0]["uid"]
    dec = client_a.post(
        "/api/access/admin/decide",
        json={"uid": uid, "decision": "allow"},
    )
    assert dec.status_code == 200, dec.text
    assert "asr/auth/accounts.json" in shared_gcs

    # --- Instance B: paid opens after GCS refresh ---
    _bind_root(monkeypatch, root_b)
    assert ag.user_may_use_paid(uid, email="user@example.com") is True
    st3 = client_b.get("/api/access/status").json()
    assert st3.get("can_use_paid") is True
    assert st3.get("status") == "allowed"
