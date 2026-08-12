"""stale pipeline_version 정책 계약."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import Figure, PaperSession, Sentence


def test_status_exposes_pipeline() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.40"
    assert st["pipeline_version"] == PIPELINE_VERSION


def test_list_marks_stale(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    pc._write_index(
        {
            "version": 1,
            "entries": [
                {
                    "id": "aaaaaaaaaaaa",
                    "title": "Old Paper Title That Is Long Enough",
                    "title_key": "old paper title that is long enough",
                    "source": "pdf",
                    "updated_at": "t",
                    "sentence_count": 1,
                    "figure_count": 0,
                    "debone": True,
                    "pipeline_version": "rich-v0",
                },
                {
                    "id": "bbbbbbbbbbbb",
                    "title": "Fresh Paper Title That Is Long Enough",
                    "title_key": "fresh paper title that is long enough",
                    "source": "pdf",
                    "updated_at": "u",
                    "sentence_count": 1,
                    "figure_count": 0,
                    "debone": True,
                    "pipeline_version": PIPELINE_VERSION,
                },
            ],
        }
    )
    listed = pc.list_cached_papers()
    by_id = {e["id"]: e for e in listed}
    assert by_id["aaaaaaaaaaaa"]["stale"] is True
    assert by_id["bbbbbbbbbbbb"]["stale"] is False


def test_try_cache_hit_skips_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    from sentence_reading.api import app as api

    monkeypatch.setattr(
        api,
        "find_cached_by_text",
        lambda text, source="pdf": {
            "id": "aaaaaaaaaaaa",
            "pipeline_version": "ancient",
        },
    )
    assert api._try_cache_hit("x" * 40, "pdf") is None


def test_open_stale_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    cid = "dddddddddddd"
    paper = tmp_path / cid
    paper.mkdir()
    (paper / "session.json").write_text(
        __import__("json").dumps(
            {
                "version": 1,
                "pipeline_version": "rich-v0",
                "title": "Stale Open Title Long Enough XX",
                "title_key": "stale open title long enough xx",
                "source": "pdf",
                "debone": True,
                "sentences": [{"id": "s1", "text": "Hello.", "section": None}],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(app)
    res = client.post(f"/api/cache/papers/{cid}/open")
    assert res.status_code == 200
    body = res.json()
    assert body["stale"] is True
    assert "stale_pipeline" in body["warnings"]
    # design/42 — KO 없으면 translate_missing 경고가 함께 올 수 있음
    assert body["current_pipeline"] == PIPELINE_VERSION


def test_ui_stale_wiring() -> None:
    app_js = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")
    assert "갱신 필요" in app_js
    assert "is-stale" in app_js
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
        / "styles.css"
    ).read_text(encoding="utf-8")
    assert ".library-item-btn.is-stale" in css


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
