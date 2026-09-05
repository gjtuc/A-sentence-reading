# -*- coding: utf-8 -*-
"""design/173c — ingest worker Cloud Run service (light HTTP + pipeline)."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from sentence_reading.llm.ingest_jobs_gcs import (
    ingest_worker_secret,
    worker_instance_id,
)

log = logging.getLogger(__name__)

app = FastAPI(title="A-sentence-reading-worker", version="0.3.156")


def _check_worker_secret(header: str) -> None:
    expected = ingest_worker_secret()
    if not expected or (header or "").strip() != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/api/status")
def worker_status() -> dict[str, Any]:
    return {
        "ok": True,
        "service_role": "worker",
        "worker_instance_id": worker_instance_id(),
        "ingest_inline": True,
    }


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/internal/run-job")
async def internal_run_job(
    payload: dict[str, Any],
    x_asr_worker_secret: str = Header(default=""),
) -> JSONResponse:
    """
    Claim GCS lease + run ingest pipeline on this instance.
    Same path as design/107 reclaim — works for queued jobs (no lease) too.
    """
    _check_worker_secret(x_asr_worker_secret)
    job_id = str((payload or {}).get("job_id") or "").strip()
    owner_uid = str((payload or {}).get("owner_uid") or "").strip()
    if not job_id.startswith("job_") or not owner_uid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_request"},
        )
    # WHY: lazy import — loads pipeline + _JOBS on worker only.
    from sentence_reading.api.app import _reclaim_ingest_job_from_gcs

    ok = await _reclaim_ingest_job_from_gcs(job_id, owner_uid)
    return JSONResponse(
        {
            "ok": bool(ok),
            "job_id": job_id,
            "worker_instance_id": worker_instance_id(),
        }
    )


@app.on_event("startup")
async def _log_worker_boot() -> None:
    log.info(
        "ingest worker ready role=worker instance=%s revision=%s",
        worker_instance_id(),
        (os.environ.get("K_REVISION") or "")[:64],
    )
