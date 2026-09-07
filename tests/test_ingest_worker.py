"""design/173c + design/178 — ingest worker isolation gate + wake evidence."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sentence_reading.llm import ingest_jobs_gcs as ij
from sentence_reading.llm import ingest_worker_wake as iww


def test_ingest_inline_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_INGEST_INLINE", raising=False)
    assert ij.ingest_inline_enabled() is True


def test_ingest_inline_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_INGEST_INLINE", "0")
    assert ij.ingest_inline_enabled() is False


def test_worker_configured_requires_url_and_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_WORKER_URL", raising=False)
    monkeypatch.delenv("ASR_WORKER_SECRET", raising=False)
    assert ij.ingest_worker_configured() is False
    assert ij.worker_config_ok() is True  # inline default on
    monkeypatch.setenv("ASR_INGEST_INLINE", "0")
    assert ij.worker_config_ok() is False
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")
    assert ij.ingest_worker_configured() is True
    assert ij.worker_config_ok() is True
    assert ij.ingest_worker_url_set() is True
    assert ij.ingest_worker_secret_set() is True


def test_wake_not_configured_outcome(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from sentence_reading.llm import evidence_bus as eb

    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setenv("ASR_INGEST_INLINE", "0")
    monkeypatch.delenv("ASR_WORKER_URL", raising=False)
    monkeypatch.delenv("ASR_WORKER_SECRET", raising=False)
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})

    result = asyncio.run(iww.wake_ingest_worker("job_abc", "uid123456789012345678", wake_path="spawn"))
    assert result.ok is False
    assert result.outcome == "not_configured"
    kinds = [r["kind"] for r in eb.list_events(limit=20)]
    assert "worker_wake_start" in kinds
    assert "worker_wake_done" in kinds
    assert "worker_config_mismatch" in kinds
    done = [r for r in eb.list_events(limit=20) if r["kind"] == "worker_wake_done"][0]
    assert done["details"]["wake_outcome"] == "not_configured"
    assert done["details"]["has_url"] is False


def test_wake_ingest_worker_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")

    class _Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json, headers):
            assert url.endswith("/internal/run-job")
            assert json["job_id"] == "job_abc"
            assert headers["X-ASR-Worker-Secret"] == "s3cret"
            return _Resp()

    monkeypatch.setattr(iww.httpx, "AsyncClient", lambda **k: _Client())
    result = asyncio.run(
        iww.wake_ingest_worker("job_abc", "uid123456789012345678", emit=False)
    )
    assert result.ok is True
    assert result.outcome == "ok"
    assert result.http_status == 200


def test_wake_http_error_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")

    class _Resp:
        status_code = 503

        def json(self):
            return {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json, headers):
            return _Resp()

    monkeypatch.setattr(iww.httpx, "AsyncClient", lambda **k: _Client())
    result = asyncio.run(
        iww.wake_ingest_worker("job_abc", "uid123456789012345678", emit=False)
    )
    assert result.ok is False
    assert result.outcome == "http_error"
    assert result.http_status == 503


def test_wake_ok_false_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")

    class _Resp:
        status_code = 200

        def json(self):
            return {"ok": False}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json, headers):
            return _Resp()

    monkeypatch.setattr(iww.httpx, "AsyncClient", lambda **k: _Client())
    result = asyncio.run(
        iww.wake_ingest_worker("job_abc", "uid123456789012345678", emit=False)
    )
    assert result.ok is False
    assert result.outcome == "ok_false"


def test_wake_timeout_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json, headers):
            raise iww.httpx.TimeoutException("slow")

    monkeypatch.setattr(iww.httpx, "AsyncClient", lambda **k: _Client())
    result = asyncio.run(
        iww.wake_ingest_worker("job_abc", "uid123456789012345678", emit=False)
    )
    assert result.ok is False
    assert result.outcome == "timeout"
    assert result.exc_class


def test_stash_and_wake_fields_from_job() -> None:
    job: dict = {}
    result = iww.WakeResult(
        ok=False,
        outcome="not_configured",
        elapsed_ms=12,
        has_url=False,
        has_secret=True,
        configured=False,
        wake_path="reclaim",
    )
    iww.stash_wake_on_job(job, result)
    fields = iww.wake_fields_from_job(job)
    assert fields["wake_outcome"] == "not_configured"
    assert fields["wake_path"] == "reclaim"
    assert fields["wake_elapsed_ms"] == 12
    assert fields["wake_has_secret"] is True
    assert fields["wake_has_url"] is False


def test_spawn_ingest_worker_inline_creates_task(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from sentence_reading.api import app as api_app

    monkeypatch.setenv("ASR_INGEST_INLINE", "1")
    created: list[str] = []

    async def _noop():
        return None

    def _fake_create_task(coro):
        created.append("task")
        coro.close()

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
    monkeypatch.setattr(api_app, "_run_ingest_job", lambda *a, **k: _noop())
    api_app._spawn_ingest_worker(
        "job_x",
        Path("/tmp/x.pdf"),
        "x.pdf",
        "pdf",
        owner_uid="uid123456789012345678",
    )
    assert created == ["task"]


def test_pre_deploy_guard_blocks_inline_off_without_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.pre_deploy_guard as pdg

    monkeypatch.setenv("ASR_INGEST_INLINE", "0")
    monkeypatch.delenv("ASR_WORKER_URL", raising=False)
    monkeypatch.delenv("ASR_WORKER_SECRET", raising=False)
    out = pdg.run_guard(
        allow_dirty=True,
        allow_same_version=True,
        skip_fetch=True,
        ci_mode=True,
        live_data={"version": "0.3.160", "deploy_git_sha": "deadbeef"},
    )
    assert "worker_wake_env_missing_with_inline_off" in out["errors"]
