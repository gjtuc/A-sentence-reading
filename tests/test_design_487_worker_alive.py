# -*- coding: utf-8 -*-
"""design/487 - the job view says whether a worker still holds the job."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sentence_reading.llm import ingest_jobs_gcs as ij
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS


def _job(**kw) -> dict:
    return {"percent": 48, "stage": "debone", "message": "body", "done": False, **kw}


def test_a_fresh_lease_is_alive() -> None:
    job = _job()
    ij.stamp_lease(job)
    assert ij.public_job_view("job_x", job)["worker_alive"] is True


def test_an_expired_lease_is_not_alive() -> None:
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    view = ij.public_job_view("job_x", _job(lease_until=past.isoformat()))
    assert view["worker_alive"] is False


def test_a_local_worker_is_alive_without_a_lease() -> None:
    assert ij.public_job_view("job_x", _job(_local_running=True))["worker_alive"] is True


def test_a_finished_job_carries_no_flag() -> None:
    view = ij.public_job_view("job_x", _job(done=True, result={}))
    assert "worker_alive" not in view
    view = ij.public_job_view("job_x", _job(error="boom"))
    assert "worker_alive" not in view


def test_the_new_rows_are_known_kinds() -> None:
    assert {"app_visibility", "upload_queue_skip"} <= set(ALLOWED_KINDS)
