# -*- coding: utf-8 -*-
"""design/111 — fix want_chunks NameError + cache_open JSON fail-closed."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "111-fix-want-chunks-nameerror.md"
APP = ROOT / "src" / "sentence_reading" / "api" / "app.py"
PUB = ROOT / "mobile" / "pubspec.yaml"


@pytest.fixture()
def auth_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "want-chunks-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    agu.reset_gcs_uid()
    yield root
    agu.reset_gcs_uid()
    app_mod._JOBS.clear()
    app_mod._SESSIONS.clear()


def _register(client: TestClient, email: str) -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": "T"},
    )
    assert r.status_code == 200, r.text


def test_status_version_pin(auth_root):
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.42"


def test_design_111_exists():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.25" in text
    assert "want_chunks" in text


def test_pubspec_pin():
    assert "0.3.42" in PUB.read_text(encoding="utf-8")


def test_want_chunks_assignment_not_inside_comment():
    """Regression: chip 108 merged assignment into the design/80 comment."""
    text = APP.read_text(encoding="utf-8")
    assert "want_chunks = bool(job_meta.get(\"want_shadowing_chunks\"))" in text
    for line in text.splitlines():
        if "want_chunks = bool(job_meta.get" in line:
            stripped = line.lstrip()
            assert not stripped.startswith("#"), line
            assert "design/80" not in line


def test_cache_open_unexpected_error_returns_json(
    auth_root, monkeypatch: pytest.MonkeyPatch
):
    client = TestClient(app)
    _register(client, "open-fail@example.com")

    def boom(_cid: str):
        raise RuntimeError("synthetic_open_boom")

    monkeypatch.setattr(app_mod, "load_cached_session", boom)
    # Valid cache_id charset (design/121 validates before load).
    r = client.post("/api/cache/papers/deadbeef01cafe00/open")
    assert r.status_code == 500
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "cache_open_failed"
    assert "다시 시도" in (body.get("message") or "")
    # EDGE: no stack / synthetic detail leaked to client.
    assert "synthetic_open_boom" not in r.text
