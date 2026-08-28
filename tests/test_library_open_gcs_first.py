# -*- coding: utf-8 -*-
"""design/121 — library open GCS-first; no local fallback on pull fail."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.llm.typography import PIPELINE_VERSION

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "121-library-open-gcs-first.md"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
CLIENT = ROOT / "mobile" / "lib" / "api" / "client.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


@pytest.fixture()
def cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "paper_cache"
    root.mkdir()
    monkeypatch.setattr(pc, "cache_root", lambda: root)
    monkeypatch.setattr(pg, "cache_root", lambda: root)
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "gcs-first-secret")
    monkeypatch.setenv("ASR_PAPER_OPEN_REQUIRE_SENTENCES", "1")
    monkeypatch.setenv("ASR_PAPER_OPEN_GCS_FIRST", "1")
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    return root


def _write_session(root: Path, cid: str, *, sentences: list[dict], title: str = "T") -> None:
    d = root / cid
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "title": title,
        "sentences": sentences,
        "figures": [],
        "pipeline_version": PIPELINE_VERSION,
        "debone": True,
    }
    (d / "session.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


def test_design_wiring_and_status(cache_dir: Path) -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.35" in text
    assert "GCS" in text or "gcs" in text.lower()
    js = APP_JS.read_text(encoding="utf-8")
    assert "design/121" in js
    assert "data.ok === false" in js
    dart = CLIENT.read_text(encoding="utf-8")
    assert "design/121" in dart
    assert "0.3.84" in PUB.read_text(encoding="utf-8")
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.84"
    assert st.get("paper_open_gcs_first") is True


def test_refresh_pull_fail_when_gcs_ready(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_session(
        cache_dir,
        "localfull001",
        sentences=[{"id": "s1", "text": "Stale local sentence should not open."}],
    )
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: True)
    monkeypatch.setattr(pg, "download_paper_cache", lambda *_a, **_k: False)
    ok, code = pg.refresh_paper_for_open("localfull001")
    assert ok is False
    assert code == "gcs_pull_failed"


def test_open_refuses_local_when_gcs_pull_fails(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product 2A: local has sentences but GCS pull fails → 502, not 200."""
    _write_session(
        cache_dir,
        "stalefull001",
        sentences=[{"id": "s1", "text": "Should not be served after pull fail."}],
    )
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: True)
    monkeypatch.setattr(pg, "download_paper_cache", lambda *_a, **_k: False)
    r = TestClient(app).post("/api/cache/papers/stalefull001/open?translate=0")
    assert r.status_code == 502, r.text
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "gcs_pull_failed"
    assert "클라우드" in (body.get("message") or "")


def test_open_overwrites_local_from_gcs(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product 1A: GCS pull always runs and replaces local sentences."""
    _write_session(
        cache_dir,
        "overwrite001",
        sentences=[{"id": "s1", "text": "OLD local text that must be replaced."}],
    )

    called = {"n": 0}

    def fake_download(*_a, **_k) -> bool:
        called["n"] += 1
        cid = _a[0] if _a else str(_k.get("cache_id") or "overwrite001")
        _write_session(
            cache_dir,
            cid,
            sentences=[{"id": "s1", "text": "NEW cloud text after pull."}],
            title="CloudTitle",
        )
        return True

    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: True)
    monkeypatch.setattr(pg, "download_paper_cache", fake_download)
    r = TestClient(app).post("/api/cache/papers/overwrite001/open?translate=0")
    assert called["n"] >= 1, "download_paper_cache should run on open"
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    texts = [s.get("text") for s in (body.get("sentences") or [])]
    assert any("NEW cloud text" in (t or "") for t in texts)
    assert not any("OLD local" in (t or "") for t in texts)


def test_gcs_skipped_allows_local_dev_open(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When GCS is not ready, local open still works (product 4 / local-only)."""
    _write_session(
        cache_dir,
        "localdev0001",
        sentences=[{"id": "s1", "text": "Local-only open is fine without GCS."}],
    )
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: False)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        return False

    monkeypatch.setattr(pg, "download_paper_cache", boom)
    r = TestClient(app).post("/api/cache/papers/localdev0001/open?translate=0")
    assert r.status_code == 200, r.text
    assert called["n"] == 0
    assert r.json().get("ok") is True


def test_kill_switch_restores_skip_when_local_ok(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASR_PAPER_OPEN_GCS_FIRST", "0")
    _write_session(
        cache_dir,
        "killskip0001",
        sentences=[{"id": "s1", "text": "Local kept when kill is off."}],
    )
    called = {"n": 0}

    def fake_download(*_a, **_k):
        called["n"] += 1
        return False

    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: True)
    monkeypatch.setattr(pg, "download_paper_cache", fake_download)
    ok, code = pg.refresh_paper_for_open("killskip0001")
    assert ok is True
    assert code == "ok"
    assert called["n"] == 0
