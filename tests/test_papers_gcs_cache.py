"""design/159 — papers GCS list-path cache + lazy purge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sentence_reading.llm import papers_gcs as pg


@pytest.fixture(autouse=True)
def _reset_runtime_caches() -> None:
    pg.reset_papers_gcs_runtime_cache_for_tests()
    yield
    pg.reset_papers_gcs_runtime_cache_for_tests()


def test_download_remote_index_uses_ttl_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pg, "papers_index_object", lambda: "asr/users/u1/papers/index.json")
    calls: list[str] = []

    def fake_download(obj: str) -> bytes:
        calls.append(obj)
        return b'{"version":1,"entries":[{"id":"abcd1234","title":"T"}]}'

    monkeypatch.setattr(pg, "download_bytes", fake_download)
    monkeypatch.setattr(
        "sentence_reading.llm.auth_google.current_gcs_uid",
        lambda: "u1",
    )

    a = pg.download_remote_index()
    b = pg.download_remote_index()
    assert a["entries"]
    assert b["entries"]
    assert len(calls) == 1


def test_invalidate_remote_index_cache_forces_refetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pg, "papers_index_object", lambda: "asr/users/u1/papers/index.json")
    calls = {"n": 0}

    def fake_download(_obj: str) -> bytes:
        calls["n"] += 1
        return b'{"version":1,"entries":[]}'

    monkeypatch.setattr(pg, "download_bytes", fake_download)
    monkeypatch.setattr(
        "sentence_reading.llm.auth_google.current_gcs_uid",
        lambda: "u1",
    )

    pg.download_remote_index()
    pg.invalidate_remote_index_cache()
    pg.download_remote_index()
    assert calls["n"] == 2


def test_maybe_purge_expired_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    purge = MagicMock(return_value=["id1"])
    monkeypatch.setattr(
        "sentence_reading.llm.paper_retention.retention_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "sentence_reading.cache.paper_cache.purge_expired_papers",
        purge,
    )

    first = pg._maybe_purge_expired()
    second = pg._maybe_purge_expired()
    assert first == ["id1"]
    assert second == []
    assert purge.call_count == 1
