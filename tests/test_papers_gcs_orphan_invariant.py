"""design/175 — papers GCS orphan invariant (prefix delete · supersede GC · CAS)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentence_reading.llm import papers_gcs as pg


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    monkeypatch.setenv("ASR_PAPERS_INDEX_CAS", "0")
    monkeypatch.setenv("ASR_PAPERS_PREFIX_DELETE", "1")
    monkeypatch.setenv("ASR_PAPERS_SUPERSEDE_GC", "1")
    root = tmp_path / "papers"
    root.mkdir()
    monkeypatch.setattr(pg, "cache_root", lambda: root)
    import sentence_reading.cache.paper_cache as pc

    monkeypatch.setattr(pc, "cache_root", lambda: root)
    yield root


def test_merge_drops_older_id_same_title_key() -> None:
    older = {
        "id": "aaaaaaaaaaaa",
        "title": "T",
        "title_key": "t key long enough here xx",
        "source": "pdf",
        "doc_role": "main",
        "updated_at": "2020",
    }
    newer = {
        "id": "bbbbbbbbbbbb",
        "title": "T2",
        "title_key": "t key long enough here xx",
        "source": "pdf",
        "doc_role": "main",
        "updated_at": "2021",
    }
    merged = pg.merge_index_entries([older], [newer])
    assert [e["id"] for e in merged] == ["bbbbbbbbbbbb"]
    dropped = pg.merge_index_dropped_ids([older], [newer], merged=merged)
    assert dropped == ["aaaaaaaaaaaa"]


def test_delete_wipes_layout_slot_residuals(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, bytes] = {}
    cid = "cccccccccccc"
    store[f"asr/papers/{cid}/session.json"] = json.dumps(
        {"figures": [{"file": "figures/a.png"}], "title": "T", "source": "pdf"}
    ).encode()
    store[f"asr/papers/{cid}/figures/a.png"] = b"x"
    store[f"asr/papers/{cid}/layout_map.json"] = b"{}"
    store[f"asr/papers/{cid}/slot_plan.json"] = b"{}"
    store["asr/papers/index.json"] = json.dumps(
        {
            "version": 1,
            "entries": [
                {
                    "id": cid,
                    "title": "T",
                    "title_key": "t key long enough here xx",
                    "source": "pdf",
                }
            ],
        }
    ).encode()

    def up(name, data, content_type="application/octet-stream"):
        store[name] = bytes(data)
        return True

    def down(name):
        return store.get(name)

    def delete(name):
        store.pop(name, None)
        return True

    def list_under(prefix: str):
        p = prefix if prefix.endswith("/") else prefix + "/"
        # list_blobs_under receives full object prefix like asr/papers/cid/
        return [k for k in list(store.keys()) if k.startswith(p)]

    monkeypatch.setattr(pg, "upload_bytes", up)
    monkeypatch.setattr(pg, "download_bytes", down)
    monkeypatch.setattr(pg, "delete_bytes", delete)
    monkeypatch.setattr(pg, "list_blobs_under", list_under)
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        pg, "gcs_config", lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})()
    )

    stats = pg.delete_paper_cache_stats(cid)
    assert stats["ok"] is True
    assert stats.get("residual_n", 0) == 0
    assert f"asr/papers/{cid}/layout_map.json" not in store
    assert f"asr/papers/{cid}/slot_plan.json" not in store
    assert f"asr/papers/{cid}/session.json" not in store
    assert f"asr/papers/{cid}/figures/a.png" not in store
    idx = json.loads(store["asr/papers/index.json"])
    assert idx["entries"] == []


def test_upload_supersede_gc_loser(monkeypatch: pytest.MonkeyPatch, _iso: Path) -> None:
    store: dict[str, bytes] = {}
    old_id = "aaaaaaaaaaaa"
    new_id = "bbbbbbbbbbbb"
    title_key = "a sufficiently long paper title here"
    store["asr/papers/index.json"] = json.dumps(
        {
            "version": 1,
            "entries": [
                {
                    "id": old_id,
                    "title": "Old",
                    "title_key": title_key,
                    "source": "pdf",
                    "doc_role": "main",
                    "updated_at": "2020",
                }
            ],
        }
    ).encode()
    store[f"asr/papers/{old_id}/session.json"] = b"{}"
    store[f"asr/papers/{old_id}/layout_map.json"] = b"{}"

    paper = _iso / new_id
    (paper / "figures").mkdir(parents=True)
    session = {
        "version": 1,
        "pipeline_version": "rich-v3",
        "title": "A Sufficiently Long Paper Title Here",
        "title_key": title_key,
        "source": "pdf",
        "doc_role": "main",
        "debone": True,
        "created_at": "t0",
        "saved_at": "t1",
        "updated_at": "2021",
        "sentences": [{"id": "s1", "text": "Hello.", "section": None}],
        "figures": [],
    }
    (paper / "session.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # local index entry required for merge
    import sentence_reading.cache.paper_cache as pc

    pc._write_index(
        {
            "version": 1,
            "entries": [
                {
                    "id": new_id,
                    "title": session["title"],
                    "title_key": title_key,
                    "source": "pdf",
                    "doc_role": "main",
                    "updated_at": "2021",
                }
            ],
        }
    )

    gc_calls: list[str] = []

    def up(name, data, content_type="application/octet-stream"):
        store[name] = bytes(data)
        return True

    def down(name):
        return store.get(name)

    def delete(name):
        store.pop(name, None)
        return True

    def list_under(prefix: str):
        p = prefix if prefix.endswith("/") else prefix + "/"
        return [k for k in list(store.keys()) if k.startswith(p)]

    def fake_gc(cid: str, *, winner_id: str = ""):
        gc_calls.append(cid)
        wipe = pg.wipe_paper_prefix(cid)
        return {"ok": wipe.get("ok"), "cache_id": cid, "winner_id": winner_id, **wipe}

    monkeypatch.setattr(pg, "upload_bytes", up)
    monkeypatch.setattr(pg, "download_bytes", down)
    monkeypatch.setattr(pg, "delete_bytes", delete)
    monkeypatch.setattr(pg, "list_blobs_under", list_under)
    monkeypatch.setattr(pg, "gc_superseded_paper", fake_gc)
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        pg, "gcs_config", lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})()
    )

    assert pg.upload_paper_cache(new_id) is True
    assert old_id in gc_calls
    idx = json.loads(store["asr/papers/index.json"])
    assert [e["id"] for e in idx["entries"]] == [new_id]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
