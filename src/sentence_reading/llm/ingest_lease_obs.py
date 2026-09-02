"""design/169m — lease / sweeper / reclaim observability helpers.

WHY: worker_lost terminals need mem vs GCS lease age + instance id to
distinguish false kills (stale memory lease) from true orphans.
INVARIANT: details are numeric/snake only (evidence/ops _safe_details).
"""

from __future__ import annotations

import hashlib
import os
import random
from datetime import datetime, timezone
from typing import Any

_HB_SAMPLE_EVERY = 4  # ~100s at 25s interval


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def lease_age_sec(job: dict[str, Any] | None, *, now: datetime | None = None) -> int | None:
    """now - lease_until in seconds. Negative => still valid. None => no lease."""
    if not isinstance(job, dict):
        return None
    until = parse_iso(str(job.get("lease_until") or ""))
    if until is None:
        return None
    clock = now or utc_now()
    return int((clock - until).total_seconds())


def lease_tok8(job: dict[str, Any] | None) -> str:
    tok = str((job or {}).get("lease_token") or "").strip().lower()
    if not tok:
        return ""
    # evidence/ops string allowlist: [a-z][a-z0-9_]*
    hex8 = "".join(c for c in tok[:8] if c in "0123456789abcdef")
    if len(hex8) < 4:
        return ""
    return f"t{hex8}"


def cr_rev8() -> str:
    rev = (os.environ.get("K_REVISION") or os.environ.get("HOSTNAME") or "local").strip()
    digest = hashlib.sha1(rev.encode("utf-8")).hexdigest()[:8]
    return f"r{digest}"


def instance_fields() -> dict[str, Any]:
    out: dict[str, Any] = {"cr_rev8": cr_rev8()}
    return out


def mem_snapshot(job: dict[str, Any] | None, *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(job, dict):
        return {"local_running": False}
    out: dict[str, Any] = {
        "local_running": bool(job.get("_local_running")),
        **instance_fields(),
    }
    age = lease_age_sec(job, now=now)
    if age is not None:
        out["mem_lease_age_sec"] = age
    tok = lease_tok8(job)
    if tok:
        out["mem_tok8"] = tok
    from sentence_reading.llm.ingest_jobs_gcs import lease_ttl_seconds

    out["lease_ttl_s"] = int(lease_ttl_seconds())
    return out


def gcs_snapshot(
    job_id: str,
    owner_uid: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from sentence_reading.llm import ingest_jobs_gcs as ij

        gcs = ij.load_ingest_job(job_id, owner_uid=owner_uid)
    except Exception:  # noqa: BLE001
        out["gcs_lease_missing"] = True
        return out
    if not isinstance(gcs, dict):
        out["gcs_lease_missing"] = True
        return out
    out["gcs_lease_missing"] = False
    out["gcs_done"] = bool(gcs.get("done") or gcs.get("error"))
    age = lease_age_sec(gcs, now=now)
    if age is not None:
        out["gcs_lease_age_sec"] = age
    else:
        out["gcs_lease_missing"] = True
    tok = lease_tok8(gcs)
    if tok:
        out["gcs_tok8"] = tok
    return out


def should_emit_heartbeat(hb_seq: int, *, force: bool = False) -> bool:
    if force:
        return True
    if hb_seq <= 0:
        return False
    return hb_seq % _HB_SAMPLE_EVERY == 0


def should_sample_sweep_none() -> bool:
    return random.randint(1, 20) == 1


def why_sweep_none(job: dict[str, Any], *, now: datetime | None = None) -> str:
    if not isinstance(job, dict):
        return "bad_job"
    if job.get("done") or job.get("error") or job.get("_discarded"):
        return "done"
    if job.get("cancel_requested"):
        return "cancel"
    if job.get("_local_running"):
        return "local_running"
    try:
        from sentence_reading.llm.ingest_jobs_gcs import lease_expired

        if not lease_expired(job, now=now):
            return "lease_alive"
    except Exception:  # noqa: BLE001
        return "lease_check_fail"
    return "unknown"


def emit_dual(
    kind: str,
    *,
    job_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    cache_id: str = "",
    content_hash: str = "",
    stage: str = "",
    percent: int | None = None,
    message: str = "",
    details: dict[str, Any] | None = None,
    severity: str = "boundary",
    ok: bool | None = None,
) -> None:
    """Emit to evidence + ops when kind is allowlisted on each bus. Never raises."""
    det = dict(details or {})
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            kind,
            severity=severity,
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            content_hash=content_hash,
            stage=stage,
            percent=percent,
            message=(message or "")[:200],
            details=det,
            ok=ok,
            code=kind,
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        from sentence_reading.llm import ops_events as oev

        oev.emit(
            kind,
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            content_hash=content_hash,
            stage=stage,
            percent=percent,
            message=message,
            details=det,
        )
    except Exception:  # noqa: BLE001
        pass


def job_ids(job: dict[str, Any] | None) -> dict[str, str]:
    j = job if isinstance(job, dict) else {}
    return {
        "trace_id": str(j.get("trace_id") or ""),
        "cache_id": str(j.get("cache_id") or j.get("target_cache_id") or ""),
        "owner_uid": str(j.get("owner_uid") or ""),
        "content_hash": str(j.get("content_hash") or ""),
        "stage": str(j.get("stage") or "")[:40],
    }
