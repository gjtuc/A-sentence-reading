# -*- coding: utf-8 -*-
"""design/82 — shadowing practice takes."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.llm import shadowing_takes as st
from sentence_reading.llm.auth_google import (
    AuthUser,
    issue_session_token,
    reset_gcs_uid,
    set_gcs_uid,
)


@pytest.fixture()
def takes_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "takes-test-secret")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(st, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.gcs_client_ready", lambda: (False, "off")
    )
    yield tmp_path


def test_apply_take_and_full_pass(takes_env: Path) -> None:
    takes = st.empty_takes("abcd1234ef")
    takes = st.apply_take(
        takes,
        sentence_id="0",
        chunk_index=0,
        chunk_count=2,
        status="recorded",
        blob_key="shadowing|abcd1234ef|0|0|1",
        mime="audio/webm",
    )
    assert takes["sentences"]["0"]["full_pass"] is False
    takes = st.apply_take(
        takes,
        sentence_id="0",
        chunk_index=1,
        chunk_count=2,
        status="recorded",
        blob_key="shadowing|abcd1234ef|0|1|2",
        mime="audio/webm",
    )
    assert takes["sentences"]["0"]["full_pass"] is True
    pl = st.full_pass_blob_keys(takes, ["0", "1"])
    assert len(pl) == 1
    assert len(pl[0]["takes"]) == 2


def test_skip_blocks_full_pass(takes_env: Path) -> None:
    takes = st.empty_takes("abcd1234ef")
    takes = st.apply_take(
        takes,
        sentence_id="0",
        chunk_index=0,
        chunk_count=2,
        status="skipped",
    )
    takes = st.apply_take(
        takes,
        sentence_id="0",
        chunk_index=1,
        chunk_count=2,
        status="recorded",
        blob_key="k",
        mime="audio/webm",
    )
    assert takes["sentences"]["0"]["full_pass"] is False
    assert st.full_pass_blob_keys(takes, ["0"]) == []


def test_api_auth_isolation(takes_env: Path) -> None:
    user_a = AuthUser(uid="user_take_a01", email="a@example.com", name="A", picture="")
    user_b = AuthUser(uid="user_take_b02", email="b@example.com", name="B", picture="")
    client = TestClient(app_mod.app)
    r = client.get("/api/shadowing/takes/abcd1234ef")
    assert r.status_code == 401
    client.cookies.set("asr_session", issue_session_token(user_a))
    r2 = client.post(
        "/api/shadowing/takes/abcd1234ef",
        json={
            "practice_enabled": True,
            "user_id": "user_take_b02",
            "sentence_id": "0",
            "chunk_index": 0,
            "chunk_count": 1,
            "status": "skipped",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    # B must not see A's takes
    client.cookies.set("asr_session", issue_session_token(user_b))
    g = client.get("/api/shadowing/takes/abcd1234ef")
    assert g.status_code == 200
    assert g.json()["takes"]["sentences"] == {}


def test_practice_off_and_kill(takes_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user = AuthUser(uid="user_take_c03", email="c@example.com", name="C", picture="")
    client = TestClient(app_mod.app)
    client.cookies.set("asr_session", issue_session_token(user))
    r = client.post(
        "/api/shadowing/takes/abcd1234ef",
        json={"practice_enabled": False, "status": "skipped", "sentence_id": "0", "chunk_index": 0, "chunk_count": 1},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "practice_off"
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "0")
    r2 = client.get("/api/shadowing/takes/abcd1234ef")
    assert r2.status_code == 503
    st_status = client.get("/api/status").json()
    assert st_status["version"] == "0.3.9"
    assert st_status["shadowing_practice_loop"] is False


def test_invalid_cache_id_and_sentence(takes_env: Path) -> None:
    """EDGE: path traversal / bad sentence ids must not write."""
    user = AuthUser(uid="user_take_d04", email="d@example.com", name="D", picture="")
    client = TestClient(app_mod.app)
    client.cookies.set("asr_session", issue_session_token(user))
    # EDGE: too-short / traversal-like ids rejected by safe_cache_id (not routed as 404).
    bad = client.get("/api/shadowing/takes/ab")
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_cache_id"
    r = client.post(
        "/api/shadowing/takes/abcd1234ef",
        json={
            "practice_enabled": True,
            "sentence_id": "../../x",
            "chunk_index": 0,
            "chunk_count": 1,
            "status": "skipped",
        },
    )
    assert r.status_code == 400


def test_sources_mention_design() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "design" / "82-shadowing-practice-loop.md").is_file()
    html = (root / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "shadowingPracticeDialog" in html
    assert "shadowingPracticeBtn" in html
    js = (root / "src" / "sentence_reading" / "static" / "shadowing_practice.js").read_text(
        encoding="utf-8"
    )
    assert "shadowingPracticeSkip" in html
    assert "ensureChunksOrThrow" in js
    assert "PAD_MS = 2000" in js
    assert "연습 UI는 후속" not in (
        root / "src" / "sentence_reading" / "static" / "app.js"
    ).read_text(encoding="utf-8")
