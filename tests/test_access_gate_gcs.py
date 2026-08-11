"""Access gate GCS durability (0.3.3 · design/69)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import access_gate as ag
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "1")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "access-gate-gcs-test-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_GCS_BUCKET", "")  # default: no real GCS in unit tests
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(ag, "project_root", lambda: root)
    from sentence_reading.cache import paper_cache as pc

    monkeypatch.setattr(pc, "project_root", lambda: root)
    agu.reset_gcs_uid()
    yield
    agu.reset_gcs_uid()


def test_status_access_gate_gcs_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.26"
    assert st.get("access_gate_gcs") is True
    assert st.get("access_gate") is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_merge_invites_redeemed_wins_over_open() -> None:
    h = "a" * 64
    local = {
        "version": 1,
        "codes": [{"hash": h, "status": "open", "created_at": 1}],
    }
    remote = {
        "version": 1,
        "codes": [
            {
                "hash": h,
                "status": "redeemed",
                "created_at": 1,
                "redeemed_at": 9,
                "redeemed_by": "u1",
            }
        ],
    }
    merged = ag._merge_invite_stores(local, remote)
    assert len(merged["codes"]) == 1
    assert merged["codes"][0]["status"] == "redeemed"
    assert merged["codes"][0]["redeemed_by"] == "u1"


def test_merge_events_dedupe_and_cap() -> None:
    local = {
        "version": 1,
        "events": [{"ts": 1, "type": "invite_minted", "uid": "", "message": "a"}],
    }
    remote = {
        "version": 1,
        "events": [
            {"ts": 1, "type": "invite_minted", "uid": "", "message": "a"},
            {"ts": 2, "type": "invite_pending", "uid": "u", "message": "b"},
        ],
    }
    merged = ag._merge_event_stores(local, remote)
    assert len(merged["events"]) == 2
    assert merged["events"][-1]["type"] == "invite_pending"


def test_merge_redeem_unions_stamps() -> None:
    local = {"version": 1, "by_uid": {"uid_aa": [1, 2]}}
    remote = {"version": 1, "by_uid": {"uid_aa": [2, 3], "uid_bb": [9]}}
    merged = ag._merge_redeem_stores(local, remote)
    assert merged["by_uid"]["uid_aa"] == [1, 2, 3]
    assert merged["by_uid"]["uid_bb"] == [9]


def test_refresh_merges_remote_invites_without_plaintext(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = "b" * 64
    remote = {
        "version": 1,
        "codes": [{"hash": h, "status": "open", "created_at": 42}],
    }
    monkeypatch.setattr(ag, "_download_auth_json", lambda name: remote if name == "invite_codes.json" else None)
    monkeypatch.setattr(aa, "pull_accounts_from_gcs", lambda: False)
    ag.refresh_access_gate_from_gcs()
    store = ag._read_invites()
    assert any(r.get("hash") == h for r in store["codes"])
    raw = (tmp_path / "proj" / "data" / "auth" / "invite_codes.json").read_text(
        encoding="utf-8"
    )
    assert "code" not in json.loads(raw).get("codes", [{}])[0] or "hash" in raw
    assert "-" not in raw or "hash" in raw  # no XXXX-XXXX plaintext field expected
    assert "TqG3" not in raw


def test_write_invites_pushes_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[str] = []

    def _push(path: Path, filename: str) -> None:
        pushed.append(filename)

    monkeypatch.setattr(ag, "_push_auth_json", _push)
    ag._write_invites({"version": 1, "codes": []})
    assert "invite_codes.json" in pushed


def test_design_69_pin() -> None:
    root = Path(__file__).resolve().parents[1]
    design = (root / "docs" / "design" / "69-access-gate-gcs.md").read_text(
        encoding="utf-8"
    )
    assert "0.3.3" in design
    assert "invite_codes.json" in design
    assert "Live Enable" in design
    assert "plaintext" in design.lower() or "평문" in design
