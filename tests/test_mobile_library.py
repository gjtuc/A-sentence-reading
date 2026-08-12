"""Flutter mobile library list/open contract (0.3.3 · design/33 · design/62)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "62-mobile-library.md"


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ASR_KAKAO_REST_API_KEY", raising=False)
    monkeypatch.setenv("ASR_AUTH_SECRET", "mobile-library-test-secret")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_mobile_library_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.33"
    assert st["mobile_library"] is True
    assert st["mobile_email_auth"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_cache_papers_empty_and_open_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    # EDGE: empty library still ok:true (list is not a paid mutate)
    r = client.get("/api/cache/papers")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body.get("papers"), list)
    # EDGE: access gate + email auth → open requires login first
    miss = client.post("/api/cache/papers/does-not-exist-zzz/open")
    assert miss.status_code == 401
    assert miss.json().get("error") == "auth_required"
    # EDGE: gate off → missing cache is 404
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    miss2 = client.post("/api/cache/papers/does-not-exist-zzz/open")
    assert miss2.status_code == 404
    assert miss2.json().get("error") == "cache_not_found"
    empty = client.post("/api/cache/papers/%20/open")
    assert empty.status_code in (404, 400, 422)


def test_mobile_dart_library_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.33" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "/api/cache/papers" in client
    assert "listPapers" in client
    assert "openPaper" in client
    lib = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(encoding="utf-8")
    assert "LibraryController" in lib
    assert "먼저 로그인" in lib
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    # Live Enable/IPS footer removed from library UI (PR #97); contract in design.


def test_no_secrets_in_mobile_dart() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|"
        r"client_secret|private_key)",
        re.I,
    )
    for path in MOBILE.rglob("*.dart"):
        if "build" in path.parts or ".dart_tool" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert banned.search(text) is None, f"secret-like in {path}"


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.3.33" in html
