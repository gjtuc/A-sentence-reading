# -*- coding: utf-8 -*-
"""design/186 — transfer pack GCS + TTL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import transfer_pack_gcs as tpg
from sentence_reading.llm import transfer_pack_ttl as ttl


def test_safe_rel_allowlist() -> None:
    assert tpg.safe_rel_path("session.json") == "session.json"
    assert tpg.safe_rel_path("figures/a.png") == "figures/a.png"
    assert tpg.safe_rel_path("user/bookmarks.json") == "user/bookmarks.json"
    assert tpg.safe_rel_path("shadowing/chunks.json") == "shadowing/chunks.json"
    assert tpg.safe_rel_path("shadowing/voice/t1.bin") == "shadowing/voice/t1.bin"
    assert (
        tpg.safe_rel_path("item/abcd1234efgh/session.json")
        == "item/abcd1234efgh/session.json"
    )
    assert tpg.safe_rel_path("../x") is None
    assert tpg.safe_rel_path("papers/x") is None
    assert tpg.safe_rel_path("notes.json") is None
    assert tpg.safe_rel_path("item/bad/session.json") is None  # cache_id too short


def test_manifest_has_session() -> None:
    assert tpg.manifest_has_session({"session.json": {"size": 1, "sha256": "a"}})
    assert tpg.manifest_has_session(
        {"item/abcd1234efgh/session.json": {"size": 1, "sha256": "a"}}
    )
    assert not tpg.manifest_has_session(
        {"item/abcd1234efgh/source.pdf": {"size": 1, "sha256": "a"}}
    )


def test_assert_refuses_papers_and_ingest() -> None:
    assert (
        tpg.assert_deletable_pack_object(
            "asr/users/u1/papers/abc/session.json", uid="u1"
        )
        is None
    )
    assert (
        tpg.assert_deletable_pack_object(
            "asr/users/u1/ingest_jobs/j1.json", uid="u1"
        )
        is None
    )
    ok = tpg.assert_deletable_pack_object(
        "asr/users/u1/transfer_packs/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/meta.json",
        uid="u1",
    )
    assert ok is not None


def test_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSFER_PACK", "0")
    out = tpg.create_pack(cache_id="abcd1234efgh", title="t", declared_bytes=100)
    assert out["ok"] is False
    assert out["error"] == "disabled"


def test_ttl_independent_of_pack_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSFER_PACK", "0")
    monkeypatch.delenv("ASR_TRANSFER_PACK_TTL", raising=False)
    assert ttl.purge_enabled() is True
    monkeypatch.setenv("ASR_TRANSFER_PACK_TTL", "0")
    assert ttl.purge_enabled() is False


def test_should_purge_ready_expired() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    meta = {
        "status": "ready",
        "expires_at": (now - timedelta(hours=1)).isoformat(),
        "download_lease_until": "",
    }
    ok, reason = ttl.should_purge_meta(meta, now=now)
    assert ok is True
    assert reason == "ttl_expired"


def test_lease_blocks_purge() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    meta = {
        "status": "ready",
        "expires_at": (now - timedelta(hours=1)).isoformat(),
        "download_lease_until": (now + timedelta(minutes=10)).isoformat(),
    }
    ok, reason = ttl.should_purge_meta(meta, now=now)
    assert ok is False
    assert reason == "lease_alive"


def test_abandon_pending() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    meta = {
        "status": "pending",
        "updated_at": (now - timedelta(hours=30)).isoformat(),
    }
    ok, reason = ttl.should_purge_meta(meta, now=now)
    assert ok is True
    assert reason == "abandoned_pending"


def test_status_flags() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.186"
    assert st.get("transfer_pack") is True
    assert st.get("transfer_pack_ttl") is True
    assert int(st.get("transfer_pack_max_bytes") or 0) >= 200 * 1024 * 1024
    assert int(st.get("transfer_pack_piece_max") or 0) == 4 * 1024 * 1024


def test_create_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSFER_PACK", "1")
    monkeypatch.setattr(tpg, "transfer_pack_max_bytes", lambda: 1000)
    out = tpg.create_pack(cache_id="abcd1234efgh", title="t", declared_bytes=5000)
    assert out["ok"] is False
    assert out["error"] == "bytes_quota"
