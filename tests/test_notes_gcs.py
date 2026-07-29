"""notes GCS merge · encode limits · API wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.llm import notes_gcs as ng
from sentence_reading.api.app import app


def test_merge_union_and_renumber() -> None:
    a = {
        "version": 2,
        "papers": {
            "cache:1": {
                "s1": {
                    "text": [{"rev": 1, "at": "2020-01-01T00:00:00Z", "body": "A"}],
                    "voice": [],
                }
            }
        },
    }
    b = {
        "version": 2,
        "papers": {
            "cache:1": {
                "s1": {
                    "text": [
                        {"rev": 1, "at": "2020-01-02T00:00:00Z", "body": "B"},
                        {"rev": 2, "at": "2020-01-01T00:00:00Z", "body": "A"},  # dup fp
                    ],
                    "voice": [
                        {
                            "rev": 1,
                            "at": "t1",
                            "blobKey": "k1",
                            "mime": "audio/webm",
                        }
                    ],
                },
                "s2": {
                    "text": [{"rev": 1, "at": "t0", "body": "only-b"}],
                    "voice": [],
                },
            }
        },
    }
    m = ng.merge_notes_stores(a, b)
    texts = m["papers"]["cache:1"]["s1"]["text"]
    assert len(texts) == 2
    assert texts[0]["body"] == "A" and texts[0]["rev"] == 1
    assert texts[1]["body"] == "B" and texts[1]["rev"] == 2
    assert m["papers"]["cache:1"]["s2"]["text"][0]["body"] == "only-b"
    assert m["papers"]["cache:1"]["s1"]["voice"][0]["blobKey"] == "k1"


def test_merge_empty_and_garbage() -> None:
    assert ng.merge_notes_stores(None, None) == ng.empty_notes_store()
    assert ng.merge_notes_stores({"version": 2, "papers": {}}, "x")["papers"] == {}


def test_encode_size_limit() -> None:
    huge = {
        "version": 2,
        "papers": {"p": {"s": {"text": [{"rev": 1, "at": "t", "body": "x" * 3_000_000}], "voice": []}}},
    }
    assert ng.encode_notes_store(huge) is None
    assert ng.encode_notes_store(ng.empty_notes_store()) is not None


def test_decode_rejects_bad() -> None:
    assert ng.decode_notes_store(None) is None
    assert ng.decode_notes_store(b"{not json") is None
    assert ng.decode_notes_store(b'{"version":2,"papers":{}}') == ng.empty_notes_store()


def test_notes_store_object_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    assert ng.notes_store_object() == "asr/notes/store_v2.json"


def test_api_notes_sync_unavailable() -> None:
    client = TestClient(app)
    r = client.get("/api/notes/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # bucket usually unset on this PC
    if not body["available"]:
        assert body["store"] is None
    st = client.get("/api/status").json()
    assert st["version"] == "0.2.52"
    assert st["gcs"]["notes_sync"] is True
    assert st["gcs"]["voice_blob_sync"] is True
    assert st["gcs"]["papers_sync"] is True


def test_push_merges_with_fake_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    cred = tmp_path / "sa.json"
    cred.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred))

    remote = {
        "version": 2,
        "papers": {
            "pk": {
                "s": {
                    "text": [{"rev": 1, "at": "a", "body": "remote"}],
                    "voice": [],
                }
            }
        },
    }
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(ng, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(ng, "gcs_config", lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})())
    monkeypatch.setattr(ng, "download_notes_store", lambda: remote)

    def fake_upload(store):
        raw = ng.encode_notes_store(store)
        uploaded["raw"] = raw
        return True

    monkeypatch.setattr(ng, "upload_notes_store", fake_upload)
    local = {
        "version": 2,
        "papers": {
            "pk": {
                "s": {
                    "text": [{"rev": 1, "at": "b", "body": "local"}],
                    "voice": [],
                }
            }
        },
    }
    merged = ng.push_notes_store(local)
    bodies = [t["body"] for t in merged["papers"]["pk"]["s"]["text"]]
    assert bodies == ["remote", "local"]
    assert uploaded["raw"]


def test_js_merge_exported() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
        / "notes_revisions.js"
    ).read_text(encoding="utf-8")
    assert "mergeStores: mergeStores" in src
    app = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")
    assert "pullNotesFromCloud" in app
    assert "/api/notes/sync" in app


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
