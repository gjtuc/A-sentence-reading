"""design/173c — ingest worker isolation gate + wake."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sentence_reading.llm import ingest_jobs_gcs as ij


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
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")
    assert ij.ingest_worker_configured() is True


def test_wake_ingest_worker_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from sentence_reading.llm import ingest_worker_wake as iww

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
    ok = asyncio.run(iww.wake_ingest_worker("job_abc", "uid123456789012345678"))
    assert ok is True


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
    api_app._JOBS["job_testinline"] = {"owner_uid": "u" * 20}
    api_app._spawn_ingest_worker(
        "job_testinline",
        Path("nope.pdf"),
        "x.pdf",
        "pdf",
        owner_uid="u" * 20,
    )
    assert created == ["task"]


def test_spawn_ingest_worker_external_wakes(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from sentence_reading.api import app as api_app

    monkeypatch.setenv("ASR_INGEST_INLINE", "0")
    monkeypatch.setenv("ASR_WORKER_URL", "https://worker.example.run.app")
    monkeypatch.setenv("ASR_WORKER_SECRET", "s3cret")
    woke: list[str] = []

    async def _wake(job_id: str, owner_uid: str) -> bool:
        woke.append(job_id)
        return True

    monkeypatch.setattr(
        "sentence_reading.llm.ingest_worker_wake.wake_ingest_worker",
        _wake,
    )

    def _fake_create_task(coro):
        asyncio.run(coro)

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
    api_app._JOBS["job_testwake"] = {"owner_uid": "u" * 20}
    api_app._spawn_ingest_worker(
        "job_testwake",
        Path("nope.pdf"),
        "x.pdf",
        "pdf",
        owner_uid="u" * 20,
    )
    assert woke == ["job_testwake"]


def test_worker_app_run_job_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.worker import app as worker_app

    monkeypatch.setenv("ASR_WORKER_SECRET", "worker-test-secret")
    client = TestClient(worker_app.app)
    bad = client.post("/internal/run-job", json={"job_id": "job_x", "owner_uid": "u"})
    assert bad.status_code == 401


def test_status_exposes_ingest_inline_flags() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["ingest_inline"] is True
    assert "ingest_worker" in st


def test_design_173c_deploy_worker_script() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "deploy_cloud_run_worker.sh").read_text(encoding="utf-8")
    assert "ASR_SERVICE_ROLE=worker" in script
    assert "deploy_cloud_run.sh" in script
    docker = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "ASR_SERVICE_ROLE" in docker
    assert "sentence_reading.worker.app" in docker
