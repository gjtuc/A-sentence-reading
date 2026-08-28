# -*- coding: utf-8 -*-
"""design/119 — shadowing chunks/build fail-closed + pending continue."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import shadowing_chunks as sc
from sentence_reading.llm.auth_google import AuthUser, issue_session_token

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "119-shadowing-chunks-build-failclosed.md"
PRACTICE_JS = ROOT / "src" / "sentence_reading" / "static" / "shadowing_practice.js"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
MOBILE = ROOT / "mobile" / "lib" / "screens" / "shadowing_practice_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


@pytest.fixture()
def shadowing_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "chunk119-secret")
    monkeypatch.setattr(sc, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.gcs_client_ready", lambda: (False, "off")
    )
    yield tmp_path


def test_design_wiring_and_version() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    # Historical ship version for 119; later chips advance pubspec/status.
    assert "0.3.33" in text
    assert "pending" in text.lower()
    js = PRACTICE_JS.read_text(encoding="utf-8")
    assert "maxRounds" in js
    assert 'st === "pending"' in js or "status === \"pending\"" in js
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "design/119" in app_js or "pending must continue" in app_js
    # Fail-closed: banner clear only on status ok
    assert 'st === "ok"' in app_js
    dart = MOBILE.read_text(encoding="utf-8")
    assert "maxRounds" in dart
    assert "continue" in dart
    assert "0.3.82" in PUB.read_text(encoding="utf-8")
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.82"


def test_api_unexpected_exception_is_502_not_500(
    shadowing_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**kwargs):
        raise RuntimeError("simulated_backend_blowup")

    monkeypatch.setattr(sc, "build_chunk_plan", boom)
    monkeypatch.setattr(app_mod, "gemini_available", lambda: True)
    token = issue_session_token(
        AuthUser(uid="u_chunk119_a", email="a@example.com", name="A")
    )
    client = TestClient(app)
    client.cookies.set("asr_session", token)
    r = client.post(
        "/api/shadowing/chunks/chunk119aaa/build",
        json={
            "practice_enabled": True,
            "sentences": [{"id": "0", "text": "hello world alpha beta"}],
        },
    )
    assert r.status_code == 502, r.text
    body = r.json()
    assert body.get("ok") is False
    assert body.get("continue") is False
    assert body.get("error") == "build_failed"
    # SECURITY: no stack / exception text leak
    blob = str(body)
    assert "simulated_backend_blowup" not in blob
    assert "Traceback" not in blob


def test_gemini_exception_becomes_value_error(shadowing_env: Path) -> None:
    def bad_gen(system: str, user: str) -> str | None:
        raise RuntimeError("upstream")

    with pytest.raises(ValueError, match="gemini_unavailable"):
        sc.plan_sentence_chunks("a longer sentence needing gemini path here", generate=bad_gen)


def test_a_b_isolation_unchanged(shadowing_env: Path) -> None:
    def fake(system: str, user: str) -> str | None:
        text = user.split("Sentence:\n", 1)[-1].strip()
        return f'["{text.split()[0]}", "{text}"]'

    sc.build_chunk_plan(
        uid="user_a_119isol",
        cache_id="isol1190001",
        sentences=[{"id": "0", "text": "hello world from paper"}],
        generate=fake,
    )
    other = sc.load_chunk_plan(uid="user_b_119isol", cache_id="isol1190001")
    assert not other.get("sentences")
