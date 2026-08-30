"""Bookmarks GCS store — merge, purge, encode."""

from __future__ import annotations

from sentence_reading.llm import bookmarks_gcs as bg


def test_merge_bookmarks_latest_at_wins() -> None:
    a = {
        "version": 1,
        "papers": {
            "cache:p1": {
                "sentences": {
                    "introduction:1": {"at": "2026-01-01T00:00:00Z", "deleted": False},
                },
                "figures": {},
            }
        },
    }
    b = {
        "version": 1,
        "papers": {
            "cache:p1": {
                "sentences": {
                    "introduction:1": {"at": "2026-01-02T00:00:00Z", "deleted": True},
                },
                "figures": {},
            }
        },
    }
    merged = bg.merge_bookmarks_stores(a, b)
    assert "cache:p1" not in merged["papers"]


def test_merge_bookmarks_union_keys() -> None:
    a = {
        "version": 1,
        "papers": {
            "cache:p1": {
                "sentences": {"introduction:1": {"at": "t1", "deleted": False}},
                "figures": {},
            }
        },
    }
    b = {
        "version": 1,
        "papers": {
            "cache:p1": {
                "sentences": {"results:2": {"at": "t2", "deleted": False}},
                "figures": {"figure:1": {"at": "t3", "deleted": False}},
            }
        },
    }
    merged = bg.merge_bookmarks_stores(a, b)
    row = merged["papers"]["cache:p1"]
    assert "introduction:1" in row["sentences"]
    assert "results:2" in row["sentences"]
    assert row["figures"]["figure:1"]["at"] == "t3"


def test_remove_paper_bookmarks(monkeypatch) -> None:
    store = {
        "version": 1,
        "papers": {
            "cache:gone": {
                "sentences": {"introduction:1": {"at": "t", "deleted": False}},
                "figures": {},
            }
        },
    }
    uploaded: list[dict] = []

    monkeypatch.setattr(bg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(bg, "gcs_config", lambda: type("C", (), {"enabled": True})())
    monkeypatch.setattr(bg, "download_bookmarks_store", lambda: store)
    monkeypatch.setattr(
        bg,
        "upload_bookmarks_store",
        lambda s: uploaded.append(s) or True,
    )
    assert bg.remove_paper_bookmarks("cache:gone") is True
    assert uploaded
    assert "cache:gone" not in uploaded[0]["papers"]


def test_encode_size_guard() -> None:
    huge = {
        "version": 1,
        "papers": {
            f"cache:{i}": {
                "sentences": {f"introduction:{j}": {"at": "t", "deleted": False} for j in range(500)},
                "figures": {},
            }
            for i in range(200)
        },
    }
    assert bg.encode_bookmarks_store(huge) is None


def test_status_exposes_bookmarks_sync() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    with TestClient(app) as client:
        st = client.get("/api/status").json()
    gcs = st.get("gcs") or {}
    assert gcs.get("bookmarks_sync") is True
    assert "bookmarks_object" in gcs


def test_bookmarks_sync_get_empty_when_logged_out() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    with TestClient(app) as client:
        r = client.get("/api/bookmarks/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
