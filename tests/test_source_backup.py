"""원본 PDF/DOCX 백업 · 재분석 계약 (0.2.20)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import PaperSession, Sentence


def test_status_version() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.2.20"


def test_save_copies_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.upload_paper_cache",
        lambda cid: False,
    )
    src = tmp_path / "upload.pdf"
    src.write_bytes(b"%PDF-1.4 fake-source-bytes")
    session = PaperSession(
        title="A Sufficiently Long Paper Title For Cache Key",
        figures=[],
        sentences=[Sentence(id="s1", text="Hello world.", section=None)],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf", source_path=src)
    assert entry is not None
    assert entry["has_source"] is True
    cid = entry["id"]
    saved = tmp_path / cid / "source.pdf"
    assert saved.is_file()
    assert saved.read_bytes() == src.read_bytes()
    listed = {e["id"]: e for e in pc.list_cached_papers()}
    assert listed[cid]["has_source"] is True


def test_save_skips_oversized_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.upload_paper_cache",
        lambda cid: False,
    )
    src = tmp_path / "huge.pdf"
    src.write_bytes(b"%PDF-" + b"x" * 100)
    monkeypatch.setattr(pc, "SOURCE_MAX_BYTES", 50)
    session = PaperSession(
        title="Oversized Source Title Long Enough Key",
        figures=[],
        sentences=[Sentence(id="s1", text="Hello.", section=None)],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf", source_path=src)
    assert entry is not None
    assert entry["has_source"] is False
    assert not (tmp_path / entry["id"] / "source.pdf").exists()


def test_attach_backfills_missing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.upload_paper_cache",
        lambda cid: False,
    )
    cid = "eeeeeeeeeeee"
    paper = tmp_path / cid
    paper.mkdir()
    (paper / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pipeline_version": PIPELINE_VERSION,
                "title": "Backfill Title Long Enough Here XX",
                "title_key": "backfill title long enough here xx",
                "source": "pdf",
                "has_source": False,
                "sentences": [{"id": "s1", "text": "Hi.", "section": None}],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    pc._write_index(
        {
            "version": 1,
            "entries": [
                {
                    "id": cid,
                    "title": "Backfill Title Long Enough Here XX",
                    "title_key": "backfill title long enough here xx",
                    "source": "pdf",
                    "updated_at": "t",
                    "has_source": False,
                    "pipeline_version": PIPELINE_VERSION,
                }
            ],
        }
    )
    upload = tmp_path / "again.pdf"
    upload.write_bytes(b"%PDF-backfill")
    assert pc.attach_source_file(cid, upload, source="pdf") is True
    assert (paper / "source.pdf").read_bytes() == b"%PDF-backfill"
    assert pc.get_source_path(cid) is not None


def test_reanalyze_missing_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    cid = "ffffffffffff"
    (tmp_path / cid).mkdir()
    (tmp_path / cid / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pipeline_version": PIPELINE_VERSION,
                "title": "No Source Title Long Enough XXX",
                "source": "pdf",
                "sentences": [{"id": "s1", "text": "A.", "section": None}],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(app)
    res = client.post(f"/api/cache/papers/{cid}/reanalyze")
    assert res.status_code == 404
    assert res.json()["error"] == "source_missing"


def test_reanalyze_starts_job(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import asyncio

    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    cid = "aaaaaaaaaa11"
    paper = tmp_path / cid
    paper.mkdir()
    (paper / "source.pdf").write_bytes(b"%PDF-1.4 xx")
    (paper / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pipeline_version": "ancient",
                "title": "Reanalyze Title Long Enough Here",
                "source": "pdf",
                "has_source": True,
                "source_file": "source.pdf",
                "sentences": [{"id": "s1", "text": "A.", "section": None}],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    started: list = []
    pending: list = []

    async def fake_job(
        job_id, tmp_path, filename, kind, *, skip_cache=False, content_hash=None
    ):
        started.append(
            (job_id, kind, skip_cache, Path(tmp_path).read_bytes(), content_hash)
        )

    def capture_task(coro):
        pending.append(coro)

        class _T:
            pass

        return _T()

    monkeypatch.setattr("sentence_reading.api.app._run_ingest_job", fake_job)
    monkeypatch.setattr("sentence_reading.api.app.asyncio.create_task", capture_task)
    client = TestClient(app)
    res = client.post(f"/api/cache/papers/{cid}/reanalyze")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["job_id"]
    assert pending
    asyncio.run(pending[0])
    assert started
    assert started[0][1] == "pdf"
    assert started[0][2] is True
    assert started[0][3] == b"%PDF-1.4 xx"


def test_gcs_upload_includes_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    root = tmp_path / "papers"
    root.mkdir()
    monkeypatch.setattr(pc, "cache_root", lambda: root)
    monkeypatch.setattr(pg, "cache_root", lambda: root)
    store: dict[str, bytes] = {}

    def up(name, data, content_type="application/octet-stream"):
        store[name] = bytes(data)
        return True

    def down(name):
        return store.get(name)

    monkeypatch.setattr(pg, "upload_bytes", up)
    monkeypatch.setattr(pg, "download_bytes", down)
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        pg,
        "gcs_config",
        lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})(),
    )

    cid = "abcd1234ef99"
    paper = root / cid
    (paper / "figures").mkdir(parents=True)
    session = {
        "version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "title": "Source Sync Title Long Enough ZZ",
        "title_key": "source sync title long enough zz",
        "source": "pdf",
        "has_source": True,
        "source_file": "source.pdf",
        "debone": True,
        "created_at": "t0",
        "saved_at": "t1",
        "sentences": [{"id": "s1", "text": "Hello.", "section": None}],
        "figures": [],
    }
    (paper / "session.json").write_text(json.dumps(session), encoding="utf-8")
    (paper / "source.pdf").write_bytes(b"%PDF-SOURCE")
    pc._write_index(
        {
            "version": 1,
            "entries": [
                {
                    "id": cid,
                    "title": session["title"],
                    "title_key": session["title_key"],
                    "source": "pdf",
                    "updated_at": "t1",
                    "has_source": True,
                    "pipeline_version": PIPELINE_VERSION,
                }
            ],
        }
    )
    assert pg.paper_source_object(cid, "source.pdf") == f"asr/papers/{cid}/source.pdf"
    assert pg.upload_paper_cache(cid) is True
    src_keys = [k for k in store if k.endswith("/source.pdf")]
    assert src_keys
    assert store[src_keys[0]] == b"%PDF-SOURCE"


def test_ui_reanalyze_wiring() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "sentence_reading" / "static"
    app_js = (root / "app.js").read_text(encoding="utf-8")
    assert "재분석" in app_js
    assert "/reanalyze" in app_js
    assert "has_source" in app_js
    css = (root / "styles.css").read_text(encoding="utf-8")
    assert ".library-item-reanalyze" in css


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
