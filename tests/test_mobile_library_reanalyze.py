"""design/145 — mobile library reanalyze wiring (0.3.61 chip; app 0.3.70)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "145-mobile-library-reanalyze.md"


def test_status_version_pin() -> None:
    st = TestClient(app_mod.app).get("/api/status").json()
    assert st["version"] == "0.3.70"


def test_mobile_reanalyze_wiring() -> None:
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.61" in design
    assert "has_source" in design
    screen = (MOBILE / "lib/screens/library_screen.dart").read_text(encoding="utf-8")
    client = (MOBILE / "lib/api/client.dart").read_text(encoding="utf-8")
    ctrl = (MOBILE / "lib/state/library_controller.dart").read_text(encoding="utf-8")
    assert "Icons.autorenew" in screen
    assert "_reanalyze" in screen
    assert "startReanalyze" in client
    assert "reanalyzePaper" in ctrl
    assert "reanalyzing" in ctrl
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.70" in pub


def test_reanalyze_endpoint_has_paid_gate() -> None:
    app_src = (ROOT / "src/sentence_reading/api/app.py").read_text(encoding="utf-8")
    idx = app_src.find("def cache_reanalyze(request: Request, cache_id: str)")
    assert idx > 0
    assert "_paid_access_denied" in app_src[idx : idx + 400]


def test_reanalyze_translate_query_on_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """translate=0 must land in job want_translate (design/99 mobile Settings)."""
    import asyncio
    import json

    from sentence_reading.cache import paper_cache as pc
    from sentence_reading.llm.typography import PIPELINE_VERSION

    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    cid = "bbbbbbbbbb22"
    paper = tmp_path / cid
    paper.mkdir()
    (paper / "source.pdf").write_bytes(b"%PDF-1.4 xx")
    (paper / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pipeline_version": PIPELINE_VERSION,
                "title": "Translate Off Title Long Enough",
                "source": "pdf",
                "sentences": [{"id": "s1", "text": "A.", "section": None}],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    captured: list = []
    pending: list = []

    async def fake_job(
        job_id, tmp_path, filename, kind, *, skip_cache=False, content_hash=None
    ):
        from sentence_reading.api import app as ap

        captured.append(dict(ap._JOBS.get(job_id) or {}))

    def capture_task(coro):
        pending.append(coro)

        class _T:
            pass

        return _T()

    monkeypatch.setattr("sentence_reading.api.app._run_ingest_job", fake_job)
    monkeypatch.setattr("sentence_reading.api.app.asyncio.create_task", capture_task)
    client = TestClient(app_mod.app)
    res = client.post(f"/api/cache/papers/{cid}/reanalyze?translate=0")
    assert res.status_code == 200
    assert pending
    asyncio.run(pending[0])
    assert captured
    assert captured[0].get("want_translate") is False
