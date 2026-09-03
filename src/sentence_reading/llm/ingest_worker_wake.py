# -*- coding: utf-8 -*-
"""design/173c — wake external ingest worker (HTTP)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sentence_reading.llm.ingest_jobs_gcs import (
    ingest_worker_configured,
    ingest_worker_secret,
    ingest_worker_url,
)

log = logging.getLogger(__name__)


async def wake_ingest_worker(job_id: str, owner_uid: str) -> bool:
    """
    POST /internal/run-job on worker service.
    Fail-soft: False when not configured or network error (job stays queued).
    """
    jid = (job_id or "").strip()
    uid = (owner_uid or "").strip()
    if not jid or not uid:
        return False
    if not ingest_worker_configured():
        log.debug("ingest worker wake skip: not configured")
        return False
    url = f"{ingest_worker_url()}/internal/run-job"
    headers = {"X-ASR-Worker-Secret": ingest_worker_secret()}
    payload: dict[str, Any] = {"job_id": jid, "owner_uid": uid}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            log.warning(
                "ingest worker wake http %s job=%s",
                resp.status_code,
                jid[:20],
            )
            return False
        data = resp.json()
        return bool(data.get("ok"))
    except Exception as exc:  # noqa: BLE001
        log.warning("ingest worker wake failed job=%s: %s", jid[:20], exc)
        return False
