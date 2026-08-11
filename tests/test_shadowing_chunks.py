# -*- coding: utf-8 -*-
"""design/80 — shadowing chunk plans."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.llm import shadowing_chunks as sc
from sentence_reading.llm.auth_google import (
    AuthUser,
    issue_session_token,
    set_gcs_uid,
    reset_gcs_uid,
)


@pytest.fixture()
def shadowing_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "chunk-test-secret")
    monkeypatch.setattr(sc, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.gcs_client_ready", lambda: (False, "off")
    )
    yield tmp_path


def _fake_generate(system: str, user: str) -> str | None:
    # Extract sentence after "Sentence:\n"
    text = user.split("Sentence:\n", 1)[-1].strip()
    words = text.split()
    if len(words) <= 2:
        return json.dumps([text])
    mid = " ".join(words[: max(2, len(words) // 2)])
    return json.dumps([mid, text])


def test_plan_sentence_chunks_growing(shadowing_env: Path) -> None:
    chunks = sc.plan_sentence_chunks(
        "catalyst is a powerful tool",
        generate=_fake_generate,
    )
    assert chunks[0] == "catalyst is"
    assert chunks[-1] == "catalyst is a powerful tool"
    assert chunks[-1].startswith(chunks[0])


def test_plan_mixed_ko_en(shadowing_env: Path) -> None:
    text = "catalyst is 강력한 tool"
    chunks = sc.plan_sentence_chunks(text, generate=_fake_generate)
    assert chunks[-1] == text
    assert "강력한" in chunks[-1]


def test_build_and_load_isolated(shadowing_env: Path) -> None:
    plan = sc.build_chunk_plan(
        uid="user_a_test01",
        cache_id="abcd1234ef",
        sentences=[{"id": "0", "text": "hello world from paper"}],
        generate=_fake_generate,
    )
    assert plan["status"] == "ok"
    set_gcs_uid("user_a_test01")
    try:
        loaded = sc.load_chunk_plan(uid="user_a_test01", cache_id="abcd1234ef")
    finally:
        reset_gcs_uid()
    assert loaded["status"] == "ok"
    # Other uid must not see A's file via wrong uid path.
    set_gcs_uid("user_b_test02")
    try:
        other = sc.load_chunk_plan(uid="user_b_test02", cache_id="abcd1234ef")
    finally:
        reset_gcs_uid()
    assert other["status"] == "empty"


def test_api_requires_auth_and_practice_flag(shadowing_env: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    user = AuthUser(uid="user_api_01", email="a@example.com", name="A", picture="")
    token = issue_session_token(user)
    client = TestClient(app_mod.app)
    r = client.get("/api/shadowing/chunks/abcd1234ef")
    assert r.status_code == 401
    client.cookies.set("asr_session", token)
    r2 = client.post(
        "/api/shadowing/chunks/abcd1234ef/build",
        json={"practice_enabled": False, "sentences": [{"id": "0", "text": "a b c d"}]},
    )
    assert r2.status_code == 400
    assert r2.json().get("error") == "practice_off"
    monkeypatch.setattr(
        "sentence_reading.api.app.gemini_available", lambda: True
    )
    monkeypatch.setattr(sc, "plan_sentence_chunks", lambda text, generate=None: [text])
    r4 = client.post(
        "/api/shadowing/chunks/abcd1234ef/build",
        json={
            "practice_enabled": True,
            "sentences": [{"id": "0", "text": "a b c d e f"}],
        },
    )
    assert r4.status_code == 200
    body = r4.json()
    assert body["ok"] is True
    assert body["plan"]["status"] == "ok"


def test_kill_off_rejects(shadowing_env: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "0")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    user = AuthUser(uid="user_api_02", email="b@example.com", name="B", picture="")
    token = issue_session_token(user)
    client = TestClient(app_mod.app)
    client.cookies.set("asr_session", token)
    r = client.get("/api/shadowing/chunks/abcd1234ef")
    assert r.status_code == 503
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.7"
    assert st["shadowing_chunks"] is False


def test_sources_mention_design() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "design" / "80-shadowing-chunks.md").is_file()
    html = (root / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "shadowingChunksBanner" in html
    js = (root / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "ensureShadowingChunks" in js
    dart = (root / "mobile" / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "fetchShadowingChunks" in dart
    assert "buildShadowingChunks" in dart


def test_api_isolation_a_b(shadowing_env: Path, monkeypatch) -> None:
    """User B must not see User A's chunk plan (empty for B)."""
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr("sentence_reading.api.app.gemini_available", lambda: True)
    monkeypatch.setattr(sc, "plan_sentence_chunks", lambda text, generate=None: [text])

    user_a = AuthUser(uid="user_iso_a01", email="a@example.com", name="A", picture="")
    user_b = AuthUser(uid="user_iso_b02", email="b@example.com", name="B", picture="")
    tok_a = issue_session_token(user_a)
    tok_b = issue_session_token(user_b)
    client = TestClient(app_mod.app)

    client.cookies.set("asr_session", tok_a)
    r = client.post(
        "/api/shadowing/chunks/abcd1234ef/build",
        json={
            "practice_enabled": True,
            "sentences": [{"id": "0", "text": "isolation check sentence here"}],
        },
    )
    assert r.status_code == 200
    assert r.json()["plan"]["status"] == "ok"

    # Switch to B — same cache_id must not leak A's plan.
    client.cookies.set("asr_session", tok_b)
    g = client.get("/api/shadowing/chunks/abcd1234ef")
    assert g.status_code == 200
    assert g.json()["plan"]["status"] == "empty"


def test_reject_path_traversal_cache_id(shadowing_env: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    user = AuthUser(uid="user_path_01", email="p@example.com", name="P", picture="")
    token = issue_session_token(user)
    client = TestClient(app_mod.app)
    client.cookies.set("asr_session", token)
    r = client.get("/api/shadowing/chunks/../etc/passwd")
    # WHY: Starlette may 404 the route before handler; either way must not succeed.
    assert r.status_code in (400, 404)
    if r.status_code == 400:
        assert r.json().get("error") == "invalid_cache_id"
    r2 = client.get("/api/shadowing/chunks/..%2Fetc")
    assert r2.status_code in (400, 404)
    r3 = client.get("/api/shadowing/chunks/short")
    assert r3.status_code == 400
    assert r3.json().get("error") == "invalid_cache_id"


def test_body_user_id_ignored(shadowing_env: Path, monkeypatch) -> None:
    """Server must use session uid only — body user_id must not redirect storage."""
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr("sentence_reading.api.app.gemini_available", lambda: True)
    monkeypatch.setattr(sc, "plan_sentence_chunks", lambda text, generate=None: [text])
    user = AuthUser(uid="user_sess_01", email="s@example.com", name="S", picture="")
    token = issue_session_token(user)
    client = TestClient(app_mod.app)
    client.cookies.set("asr_session", token)
    r = client.post(
        "/api/shadowing/chunks/abcd1234ef/build",
        json={
            "practice_enabled": True,
            "user_id": "user_other_99",
            "sentences": [{"id": "0", "text": "session uid only please"}],
        },
    )
    assert r.status_code == 200
    # Plan stored under session uid, not body user_id.
    set_gcs_uid("user_sess_01")
    try:
        plan = sc.load_chunk_plan(uid="user_sess_01", cache_id="abcd1234ef")
    finally:
        reset_gcs_uid()
    assert plan["status"] == "ok"
    set_gcs_uid("user_other_99")
    try:
        other = sc.load_chunk_plan(uid="user_other_99", cache_id="abcd1234ef")
    finally:
        reset_gcs_uid()
    assert other["status"] == "empty"
