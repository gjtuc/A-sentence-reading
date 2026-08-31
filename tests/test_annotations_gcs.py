"""Annotations GCS store — merge, purge, encode."""

from __future__ import annotations

from sentence_reading.llm import annotations_gcs as ag


def test_merge_annotations_latest_at_wins() -> None:
    a = {
        "version": 1,
        "papers": {
            "cache:p1": {
                "sentences": {
                    "introduction:1": [
                        {
                            "id": "ann-1",
                            "at": "2026-01-01T00:00:00Z",
                            "kind": "highlight",
                            "color": "yellow",
                            "sentence_id": "s1",
                        }
                    ]
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
                    "introduction:1": [
                        {
                            "id": "ann-1",
                            "at": "2026-01-02T00:00:00Z",
                            "deleted": True,
                            "kind": "highlight",
                            "sentence_id": "s1",
                        }
                    ]
                },
                "figures": {},
            }
        },
    }
    merged = ag.merge_annotations_stores(a, b)
    assert "cache:p1" not in merged["papers"]


def test_merge_annotations_union_keys() -> None:
    a = {
        "version": 1,
        "papers": {
            "cache:p1": {
                "sentences": {
                    "introduction:1": [
                        {
                            "id": "a1",
                            "at": "t1",
                            "kind": "highlight",
                            "color": "yellow",
                            "sentence_id": "s1",
                        }
                    ]
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
                    "results:2": [
                        {
                            "id": "a2",
                            "at": "t2",
                            "kind": "note",
                            "note": "memo",
                            "sentence_id": "s2",
                        }
                    ]
                },
                "figures": {
                    "figure:1": [
                        {
                            "id": "f1",
                            "at": "t3",
                            "kind": "ink",
                            "paths": [],
                        }
                    ]
                },
            }
        },
    }
    merged = ag.merge_annotations_stores(a, b)
    row = merged["papers"]["cache:p1"]
    assert "introduction:1" in row["sentences"]
    assert "results:2" in row["sentences"]
    assert row["figures"]["figure:1"][0]["id"] == "f1"


def test_remove_paper_annotations(monkeypatch) -> None:
    store = {
        "version": 1,
        "papers": {
            "cache:gone": {
                "sentences": {
                    "introduction:1": [
                        {
                            "id": "a1",
                            "at": "t",
                            "kind": "highlight",
                            "color": "yellow",
                            "sentence_id": "s1",
                        }
                    ]
                },
                "figures": {},
            }
        },
    }
    uploaded: list[dict] = []

    monkeypatch.setattr(ag, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(ag, "gcs_config", lambda: type("C", (), {"enabled": True})())
    monkeypatch.setattr(ag, "download_annotations_store", lambda: store)
    monkeypatch.setattr(
        ag,
        "upload_annotations_store",
        lambda s: uploaded.append(s) or True,
    )
    assert ag.remove_paper_annotations("cache:gone") is True
    assert uploaded
    assert "cache:gone" not in uploaded[0]["papers"]


def test_encode_rejects_oversize() -> None:
    huge = {
        "version": 1,
        "papers": {
            "cache:x": {
                "sentences": {
                    "body:1": [
                        {
                            "id": "big",
                            "at": "t",
                            "kind": "note",
                            "note": "x" * 3_000_000,
                            "sentence_id": "s1",
                        }
                    ]
                },
                "figures": {},
            }
        },
    }
    assert ag.encode_annotations_store(huge) is None
