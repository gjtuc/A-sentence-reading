"""papers GCS path · index merge · API list/open wiring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import papers_gcs as pg


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    root = tmp_path / "papers"
    root.mkdir()
    monkeypatch.setattr(pg, "cache_root", lambda: root)
    # paper_cache module uses its own cache_root — patch both
    import sentence_reading.cache.paper_cache as pc

    monkeypatch.setattr(pc, "cache_root", lambda: root)
    yield root


def test_object_paths() -> None:
    assert pg.papers_index_object() == "asr/papers/index.json"
    assert pg.paper_session_object("abc123def456") == "asr/papers/abc123def456/session.json"
    assert (
        pg.paper_figure_object("abc123def456", "figures/fig-0001.png")
        == "asr/papers/abc123def456/figures/fig-0001.png"
    )
    assert pg.paper_session_object("../x") is None
    assert pg.paper_figure_object("abc123def456", "figures/../../etc") is None
    assert pg.paper_figure_object("abc123def456", "session.json") is None


def test_merge_index_keeps_newer() -> None:
    a = [{"id": "aaaaaaaaaaaa", "title": "T", "title_key": "t key long enough here xx", "source": "pdf", "updated_at": "2020"}]
    b = [{"id": "aaaaaaaaaaaa", "title": "T2", "title_key": "t key long enough here xx", "source": "pdf", "updated_at": "2021"}]
    m = pg.merge_index_entries(a, b)
    assert len(m) == 1
    assert m[0]["title"] == "T2"


def test_upload_download_roundtrip(monkeypatch: pytest.MonkeyPatch, _iso: Path) -> None:
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
        pg, "gcs_config", lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})()
    )

    cid = "abcd1234ef00"
    paper = _iso / cid
    (paper / "figures").mkdir(parents=True)
    session = {
        "version": 1,
        "pipeline_version": "rich-v3",
        "title": "A Sufficiently Long Paper Title Here",
        "title_key": "a sufficiently long paper title here",
        "source": "pdf",
        "debone": True,
        "created_at": "t0",
        "saved_at": "t1",
        "sentences": [{"id": "s1", "text": "Hello.", "section": None}],
        "figures": [{"id": "fig-0001", "caption": "", "page_index": 0, "file": "figures/fig-0001.png"}],
    }
    (paper / "session.json").write_text(json.dumps(session), encoding="utf-8")
    (paper / "figures" / "fig-0001.png").write_bytes(b"PNGDATA")
    # local index entry
    import sentence_reading.cache.paper_cache as pc

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
                    "created_at": "t0",
                    "sentence_count": 1,
                    "figure_count": 1,
                    "debone": True,
                    "pipeline_version": "rich-v3",
                }
            ],
        }
    )

    assert pg.upload_paper_cache(cid) is True
    assert any(k.endswith("/session.json") for k in store)
    # wipe local and re-download
    import shutil

    shutil.rmtree(paper)
    assert pg.download_paper_cache(cid) is True
    assert ( _iso / cid / "session.json").is_file()
    assert (_iso / cid / "figures" / "fig-0001.png").read_bytes() == b"PNGDATA"


def test_pull_matching_text(monkeypatch: pytest.MonkeyPatch, _iso: Path) -> None:
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        pg, "gcs_config", lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})()
    )
    title_key = "unique enough title key for matching zz"
    entry = {
        "id": "bbbbbbbbbbbb",
        "title": "Unique Enough Title Key For Matching ZZ",
        "title_key": title_key,
        "source": "pdf",
        "updated_at": "t",
        "pipeline_version": "rich-v3",
    }
    monkeypatch.setattr(
        pg, "download_remote_index", lambda: {"version": 1, "entries": [entry]}
    )
    monkeypatch.setattr(pg, "download_paper_cache", lambda cid, entry=None: True)
    text = "Abstract " + title_key + " more text"
    hit = pg.pull_paper_matching_text(text, source="pdf")
    assert hit and hit["id"] == "bbbbbbbbbbbb"


def test_status_and_list_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.api.app.list_cached_papers",
        lambda: [{"id": "x", "title": "T", "source": "pdf", "updated_at": "", "sentence_count": 0, "figure_count": 0, "debone": False}],
    )
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.list_merged_paper_entries",
        lambda: [{"id": "y", "title": "Cloud", "source": "pdf", "updated_at": "t", "sentence_count": 1, "figure_count": 0, "debone": True}],
    )
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.21"
    assert st.get("pipeline_version")
    papers = client.get("/api/cache/papers").json()["papers"]
    assert papers[0]["id"] == "y"


def test_delete_paper_updates_remote_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        pg, "gcs_config", lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})()
    )
    store: dict[str, bytes] = {}
    cid = "cccccccccccc"
    sess = {
        "figures": [{"file": "figures/a.png"}],
        "title": "T",
    }
    store[f"asr/papers/{cid}/session.json"] = json.dumps(sess).encode()
    store[f"asr/papers/{cid}/figures/a.png"] = b"x"
    store["asr/papers/index.json"] = json.dumps(
        {"version": 1, "entries": [{"id": cid, "title": "T", "title_key": "t", "source": "pdf"}]}
    ).encode()

    def up(name, data, content_type="application/octet-stream"):
        store[name] = bytes(data)
        return True

    def down(name):
        return store.get(name)

    def delete(name):
        store.pop(name, None)
        return True

    monkeypatch.setattr(pg, "upload_bytes", up)
    monkeypatch.setattr(pg, "download_bytes", down)
    monkeypatch.setattr(pg, "delete_bytes", delete)
    assert pg.delete_paper_cache(cid) is True
    assert f"asr/papers/{cid}/session.json" not in store
    idx = json.loads(store["asr/papers/index.json"])
    assert idx["entries"] == []


def test_prompt_text_updated() -> None:
    html = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert "여러 사람에게 새로 들려준다고" in html
    assert "마치 여러 사람에게" not in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
