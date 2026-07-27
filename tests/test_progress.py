"""M5 진행 복원 계약 (0.2.23) — progress.js 규칙 미러 + API."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import _file_sha256, app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import PaperSession, Sentence


def clamp_index(i: object, n: int) -> int:
    if not n or n < 1:
        return 0
    try:
        x = int(i)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if x < 0:
        return 0
    if x >= n:
        return n - 1
    return x


def progress_keys_for(paper: dict) -> list[str]:
    keys: list[str] = []
    if paper.get("cacheId"):
        keys.append(f"cache:{paper['cacheId']}")
    h = paper.get("contentHash") or paper.get("content_hash")
    if h and re.fullmatch(r"[a-f0-9]{64}", str(h), flags=re.I):
        keys.append(f"hash:{str(h).lower()}")
    if paper.get("sessionId"):
        keys.append(f"ses:{paper['sessionId']}")
    elif paper.get("id") and not paper.get("cacheId"):
        keys.append(f"id:{paper['id']}")
    return keys


def test_status_progress_flag() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.2.23"
    assert st["progress_restore"] is True


def test_clamp_edge_cases() -> None:
    assert clamp_index(-3, 10) == 0
    assert clamp_index(99, 10) == 9
    assert clamp_index("nope", 5) == 0
    assert clamp_index(2, 0) == 0
    assert clamp_index(1.9, 5) == 1


def test_progress_keys_priority() -> None:
    h = "a" * 64
    keys = progress_keys_for(
        {"cacheId": "cid1", "contentHash": h, "sessionId": "ses1"}
    )
    assert keys[0] == "cache:cid1"
    assert keys[1] == f"hash:{h}"
    assert keys[2] == "ses:ses1"
    assert progress_keys_for({"contentHash": "short"}) == []
    assert progress_keys_for({}) == []


def test_file_sha256(tmp_path: Path) -> None:
    p = tmp_path / "x.pdf"
    raw = b"%PDF-progress-test"
    p.write_bytes(raw)
    assert _file_sha256(p) == hashlib.sha256(raw).hexdigest()
    assert _file_sha256(tmp_path / "missing.pdf") is None


def test_save_stores_content_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.upload_paper_cache",
        lambda cid: False,
    )
    h = "b" * 64
    session = PaperSession(
        title="Progress Hash Title Long Enough Here",
        figures=[],
        sentences=[Sentence(id="s1", text="Hello.", section=None)],
    )
    entry = pc.save_paper_session(
        session, debone=True, source="pdf", content_hash=h
    )
    assert entry is not None
    assert entry["content_hash"] == h
    meta = json.loads(
        (tmp_path / entry["id"] / "session.json").read_text(encoding="utf-8")
    )
    assert meta["content_hash"] == h
    loaded = pc.load_cached_session(entry["id"])
    assert loaded is not None
    assert loaded[1]["content_hash"] == h


def test_open_returns_content_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    cid = "proghash0001"
    paper = tmp_path / cid
    paper.mkdir()
    h = "c" * 64
    (paper / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pipeline_version": PIPELINE_VERSION,
                "title": "Open Hash Title Long Enough XXX",
                "source": "pdf",
                "content_hash": h,
                "sentences": [{"id": "s1", "text": "A.", "section": None}],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(app)
    res = client.post(f"/api/cache/papers/{cid}/open")
    assert res.status_code == 200
    assert res.json()["content_hash"] == h


def test_ui_progress_wiring() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
    )
    prog = (root / "progress.js").read_text(encoding="utf-8")
    assert "asr.progress.v1" in prog
    assert "applyStoredProgress" in prog
    assert "hash:" in prog
    app_js = (root / "app.js").read_text(encoding="utf-8")
    assert "AsrProgress" in app_js
    assert "persistReadingProgress" in app_js
    assert "contentHash" in app_js
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "progress.js" in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
