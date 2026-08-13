"""Flutter mobile reader + cursor PATCH (0.3.3 · design/33 · design/63)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app, _SESSIONS
from sentence_reading.models import build_mock_session

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "63-mobile-reader.md"


def test_status_mobile_reader_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.47"
    assert st["mobile_reader"] is True
    assert st["mobile_library"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_session_cursor_patch_independent() -> None:
    client = TestClient(app)
    session = build_mock_session()
    sid = "ses_test_cursor_071"
    _SESSIONS[sid] = session
    try:
        session.sentence_index = 0
        session.figure_index = 0
        r = client.patch(f"/api/session/{sid}/cursor", json={"sentence_index": 2})
        assert r.status_code == 200
        body = r.json()
        assert body["sentence_index"] == 2
        assert body["figure_index"] == 0
        r2 = client.patch(f"/api/session/{sid}/cursor", json={"figure_index": 1})
        assert r2.status_code == 200
        assert r2.json()["sentence_index"] == 2
        assert r2.json()["figure_index"] == 1
        bad = client.patch(
            f"/api/session/{sid}/cursor", json={"sentence_index": "nope"}
        )
        assert bad.status_code == 400
        miss = client.patch(
            "/api/session/does-not-exist/cursor", json={"sentence_index": 0}
        )
        assert miss.status_code == 404
        huge = client.patch(
            f"/api/session/{sid}/cursor",
            json={"sentence_index": 9999, "figure_index": -1},
        )
        assert huge.status_code == 200
        h = huge.json()
        assert 0 <= h["sentence_index"] < h["sentence_count"]
        assert 0 <= h["figure_index"] < h["figure_count"]
    finally:
        _SESSIONS.pop(sid, None)


def test_mobile_dart_reader_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.47" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "patchCursor" in client
    assert "/api/session/" in client
    models = (MOBILE / "lib" / "api" / "reading_models.dart").read_text(encoding="utf-8")
    assert "advanceSentence" in models and "advanceFigure" in models
    assert "INVARIANT" in models
    reader = (MOBILE / "lib" / "screens" / "reader_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "advanceSentence" in reader and "advanceFigure" in reader
    # design/93 — user-facing Live Enable / IPS footer removed
    assert "Live Enable" not in reader
    assert "Trading Gate" not in reader
    # design/94 — zoom uses full figure frame
    assert "_ZoomableFigureFrame" in reader
    # design/95 — swipe pager
    assert "_SwipePager" in reader
    # design/97 — double-tap expand
    assert "_ReaderLayoutMode" in reader
    assert "onDoubleTapExpand" in reader
    # design/98 — draggable split
    assert "_SplitHandle" in reader
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in design
    assert "Trading Gate" in design or "ASR" in design


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
    assert "app.js?v=0.3.47" in html
