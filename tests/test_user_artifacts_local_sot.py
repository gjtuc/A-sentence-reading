"""design/187 — user artifacts local SoT flags, refuse push, migrate-ack routes."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ASR_BOOKMARKS_LOCAL_SOT", "1")
    monkeypatch.setenv("ASR_ANNOTATIONS_LOCAL_SOT", "1")
    monkeypatch.setenv("ASR_SHADOWING_LOCAL_SOT", "1")
    monkeypatch.setenv("ASR_NOTES_LOCAL_SOT", "1")
    from sentence_reading.api.app import app

    return TestClient(app)


def test_status_advertises_local_sot(client: TestClient) -> None:
    st = client.get("/api/status").json()
    assert st.get("bookmarks_local_sot") is True
    assert st.get("annotations_local_sot") is True
    assert st.get("shadowing_local_sot") is True
    assert st.get("notes_local_sot") is True
    assert st["version"] == "0.3.184"


def test_bookmarks_put_refused(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.api.app.gcs_status",
        lambda: {
            "enabled": True,
            "ready": True,
            "bookmarks_object": "users/u/bookmarks/store_v1.json",
        },
    )
    monkeypatch.setattr("sentence_reading.api.app.auth_enabled", lambda: False)
    res = client.put("/api/bookmarks/sync", json={"store": {"version": 1, "papers": {}}})
    assert res.status_code == 409
    assert res.json().get("error") == "bookmarks_local_sot"


def test_kill_allows_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_BOOKMARKS_LOCAL_SOT", "0")
    from sentence_reading.llm.bookmarks_gcs import refuse_bookmarks_push_if_local_sot

    assert refuse_bookmarks_push_if_local_sot() is None


def test_version_flags_module() -> None:
    os.environ["ASR_BOOKMARKS_LOCAL_SOT"] = "1"
    from sentence_reading.llm.user_artifacts_local_sot import status_fields

    f = status_fields()
    assert f["bookmarks_local_sot"] is True
