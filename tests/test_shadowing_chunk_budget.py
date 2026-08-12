# -*- coding: utf-8 -*-
"""design/113 — shadowing chunk build time budget + resume (no gateway 504)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import shadowing_chunks as sc
from sentence_reading.llm.auth_google import (
    AuthUser,
    issue_session_token,
    reset_gcs_uid,
    set_gcs_uid,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "113-shadowing-chunk-budget.md"
PUB = ROOT / "mobile" / "pubspec.yaml"


@pytest.fixture()
def shadowing_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "budget-test-secret")
    monkeypatch.setenv("ASR_SHADOWING_CHUNK_BUDGET_S", "90")
    monkeypatch.setattr(sc, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.gcs_client_ready", lambda: (False, "off")
    )
    yield tmp_path


def _fake_generate(system: str, user: str) -> str | None:
    text = user.split("Sentence:\n", 1)[-1].strip()
    words = text.split()
    if len(words) <= 2:
        return json.dumps([text])
    mid = " ".join(words[: max(2, len(words) // 2)])
    return json.dumps([mid, text])


def _slow_generate(system: str, user: str) -> str | None:
    time.sleep(0.05)
    return _fake_generate(system, user)


def test_design_113_and_version_pin(shadowing_env: Path):
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.27" in text
    assert "ASR_SHADOWING_CHUNK_BUDGET_S" in text
    assert "504" in text
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.31"
    assert st.get("shadowing_chunk_budget") is True
    assert "0.3.31" in PUB.read_text(encoding="utf-8")


def test_budget_returns_pending_then_resume(shadowing_env: Path):
    rows = [
        {"id": str(i), "text": f"catalyst sample sentence number {i} here"}
        for i in range(8)
    ]
    # Tiny budget → at most a couple sentences per slice.
    p1 = sc.build_chunk_plan(
        uid="user_budget_a01",
        cache_id="budgetcid01",
        sentences=rows,
        generate=_slow_generate,
        budget_s=0.08,
        resume=True,
    )
    assert p1["status"] == "pending"
    assert 0 < len(p1["sentences"]) < 8
    done1 = len(p1["sentences"])

    p2 = sc.build_chunk_plan(
        uid="user_budget_a01",
        cache_id="budgetcid01",
        sentences=rows,
        generate=_fake_generate,
        budget_s=90,
        resume=True,
    )
    assert p2["status"] == "ok"
    assert len(p2["sentences"]) == 8
    # Resume kept earlier ids.
    assert done1 <= len(p2["sentences"])


def test_owner_isolation_pending(shadowing_env: Path):
    rows = [{"id": "0", "text": "hello world from paper one"}]
    sc.build_chunk_plan(
        uid="user_iso_aaa01",
        cache_id="isocid0001",
        sentences=rows,
        generate=_fake_generate,
    )
    set_gcs_uid("user_iso_bbb02")
    try:
        other = sc.load_chunk_plan(uid="user_iso_bbb02", cache_id="isocid0001")
    finally:
        reset_gcs_uid()
    assert other.get("status") in ("empty", None) or not other.get("sentences")


def test_api_build_pending_is_200(shadowing_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "budget-test-secret")
    # Force pending from build.
    def fake_build(**kwargs):
        return {
            "version": 1,
            "cache_id": kwargs["cache_id"],
            "status": "pending",
            "error": None,
            "sentences": {"0": {"text": "a b c d e", "chunks": ["a b", "a b c d e"]}},
            "progress": {"done": 1, "total": 5},
        }

    monkeypatch.setattr(sc, "build_chunk_plan", lambda **k: fake_build(**k))
    monkeypatch.setattr(
        "sentence_reading.api.app.gemini_available", lambda: True
    )
    token = issue_session_token(
        AuthUser(uid="u_budget_api_01", email="b@example.com", name="B")
    )
    client = TestClient(app)
    client.cookies.set("asr_session", token)
    r = client.post(
        "/api/shadowing/chunks/budgetapi01/build",
        json={
            "practice_enabled": True,
            "sentences": [
                {"id": str(i), "text": f"word alpha beta gamma {i}"}
                for i in range(5)
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("continue") is True
    assert body["plan"]["status"] == "pending"
    # Fail-closed: not a silent full success.
    assert body["plan"]["status"] != "ok"
