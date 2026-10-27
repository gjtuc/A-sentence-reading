# -*- coding: utf-8 -*-
"""design/470 — a device copy saved without headings asks for them once."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sentence_reading import paper_headings as ph
from sentence_reading.api import app as app_mod
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import papers_gcs as pg

_HEADS = [{"text": "1. INTRODUCTION", "from": "sent_000019"}]


def _local_paper(tmp_path, monkeypatch, cid: str, meta: dict) -> None:
    root = tmp_path / "papers"
    (root / cid).mkdir(parents=True)
    (root / cid / "session.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(pc, "cache_root", lambda: root)
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: False)


def test_stored_headings_reads_the_saved_list(tmp_path, monkeypatch) -> None:
    _local_paper(tmp_path, monkeypatch, "abcdef123456", {"headings": _HEADS, "sentences": []})
    assert ph.stored_headings("abcdef123456") == (_HEADS, "ok")


def test_stored_headings_codes(tmp_path, monkeypatch) -> None:
    _local_paper(tmp_path, monkeypatch, "abcdef123456", {"sentences": []})
    assert ph.stored_headings("abcdef123456") == ([], "ok")
    assert ph.stored_headings("zzzz99999999") == ([], "not_found")
    assert ph.stored_headings("../x") == ([], "bad_cache_id")


def test_stored_headings_prefers_the_users_gcs_copy(tmp_path, monkeypatch) -> None:
    _local_paper(tmp_path, monkeypatch, "abcdef123456", {"headings": [{"text": "Leftover", "from": "s1"}]})
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: True)
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.download_bytes",
        lambda obj, **_k: json.dumps({"headings": _HEADS}).encode("utf-8"),
    )
    assert ph.stored_headings("abcdef123456") == (_HEADS, "ok")


def test_headings_route(monkeypatch) -> None:
    monkeypatch.setattr(app_mod, "_paid_access_denied", lambda _r: None)
    monkeypatch.setattr(ph, "stored_headings", lambda cid: (_HEADS, "ok") if cid == "abcdef123456" else ([], "not_found"))
    client = TestClient(app_mod.app)
    ok = client.get("/api/cache/papers/abcdef123456/headings")
    assert ok.status_code == 200
    assert ok.json() == {"ok": True, "code": "ok", "headings": _HEADS}
    miss = client.get("/api/cache/papers/zzzz99999999/headings")
    assert miss.status_code == 404
    assert miss.json()["headings"] == []
