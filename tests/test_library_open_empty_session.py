# -*- coding: utf-8 -*-
"""design/114 — library open must not succeed with empty sentences."""
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
DESIGN = ROOT / "docs" / "design" / "114-library-open-empty-session.md"
PUB = ROOT / "mobile" / "pubspec.yaml"


@pytest.fixture()
def cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "paper_cache"
    root.mkdir()
    monkeypatch.setattr(pc, "cache_root", lambda: root)
    monkeypatch.setattr(pg, "cache_root", lambda: root)
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "open-empty-secret")
    monkeypatch.setenv("ASR_PAPER_OPEN_REQUIRE_SENTENCES", "1")
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


def test_design_and_status(cache_dir: Path):
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.28" in text
    assert "empty" in text.lower()
    st = TestClient(app).get("/api/status").json()
    # WHY: version string advances each chip; flag is the live contract for 114.
    assert st.get("paper_open_require_sentences") is True
    assert "version:" in PUB.read_text(encoding="utf-8")


def test_local_session_has_sentences(cache_dir: Path):
    _write_session(cache_dir, "abcd1234ef", sentences=[])
    assert pg.local_session_has_sentences("abcd1234ef") is False
    _write_session(
        cache_dir,
        "abcd1234ef",
        sentences=[{"id": "s1", "text": "Hello world from paper."}],
    )
    assert pg.local_session_has_sentences("abcd1234ef") is True


def test_ensure_repulls_when_local_empty(cache_dir: Path, monkeypatch: pytest.MonkeyPatch):
    _write_session(cache_dir, "repull000001", sentences=[])
    called = {"n": 0}

    def fake_download(cid: str, *, entry=None) -> bool:
        called["n"] += 1
        _write_session(
            cache_dir,
            cid,
            sentences=[{"id": "s1", "text": "Pulled sentence text here."}],
        )
        return True

    monkeypatch.setattr(pg, "download_paper_cache", fake_download)
    assert pg.ensure_paper_local("repull000001") is True
    assert called["n"] == 1
    assert pg.local_session_has_sentences("repull000001") is True


def test_open_empty_session_is_422(cache_dir: Path, monkeypatch: pytest.MonkeyPatch):
    _write_session(cache_dir, "empty0000001", sentences=[], title="OnlyTitle")
    # design/121 — skip GCS path so empty local still surfaces as 422 (114).
    monkeypatch.setattr(pg, "refresh_paper_for_open", lambda _cid: (True, "gcs_skipped"))
    monkeypatch.setattr(pg, "download_paper_cache", lambda *_a, **_k: False)
    client = TestClient(app)
    r = client.post("/api/cache/papers/empty0000001/open?translate=0")
    assert r.status_code == 422, r.text
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "empty_session"
    assert "문장" in (body.get("message") or "")


def test_open_with_sentences_ok(cache_dir: Path):
    _write_session(
        cache_dir,
        "full00000001",
        sentences=[{"id": "s1", "text": "Catalyst remains stable after pretreatment."}],
        title="OkPaper",
    )
    client = TestClient(app)
    r = client.post("/api/cache/papers/full00000001/open?translate=0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert len(body.get("sentences") or []) >= 1
