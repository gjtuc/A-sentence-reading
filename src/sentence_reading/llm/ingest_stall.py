"""design/168e — translate stall detector + sweeper env helpers.

WHY: client 504 idle must not be the only signal that a job died mid-translate.
INVARIANT:
- Never invent cache_id on terminal fail.
- Kill: ASR_INGEST_STALL_SEC=0 / ASR_INGEST_SWEEPER_SEC=0.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from sentence_reading.llm.env import load_asr_env

_DEFAULT_STALL_SEC = 300
_DEFAULT_SWEEPER_SEC = 60


def _parse_nonneg_int(raw: str | None, default: int) -> int:
    try:
        n = int(str(raw or "").strip())
    except (TypeError, ValueError):
        return default
    return max(0, n)


def translate_stall_sec() -> int:
    """Seconds of unchanged translate progress before stall. 0 = detector off."""
    load_asr_env()
    return _parse_nonneg_int(os.environ.get("ASR_INGEST_STALL_SEC"), _DEFAULT_STALL_SEC)


def sweeper_interval_sec() -> int:
    """Background sweeper sleep seconds. 0 = sweeper off."""
    load_asr_env()
    return _parse_nonneg_int(
        os.environ.get("ASR_INGEST_SWEEPER_SEC"), _DEFAULT_SWEEPER_SEC
    )


def ingest_stall_detector_enabled() -> bool:
    return translate_stall_sec() > 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(raw: str) -> datetime | None:
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


def progress_key(percent: int, message: str) -> str:
    msg = re.sub(r"\s+", " ", (message or "").strip())[:120]
    return f"{int(percent)}|{msg}"


def note_job_progress(
    job: dict[str, Any],
    *,
    percent: int | None = None,
    message: str | None = None,
    now: datetime | None = None,
) -> None:
    """Stamp _progress_ts when percent/message key changes."""
    if not isinstance(job, dict):
        return
    pct = int(percent if percent is not None else (job.get("percent") or 0))
    msg = str(message if message is not None else (job.get("message") or ""))
    key = progress_key(pct, msg)
    prev = str(job.get("_progress_key") or "")
    if key == prev and job.get("_progress_ts"):
        return
    clock = now or _utc_now()
    job["_progress_key"] = key
    job["_progress_ts"] = clock.isoformat()


def progress_idle_sec(job: dict[str, Any], *, now: datetime | None = None) -> int | None:
    """Seconds since last progress stamp, or None if unknown."""
    ts = _parse_iso(str(job.get("_progress_ts") or ""))
    if ts is None:
        return None
    clock = now or _utc_now()
    return max(0, int((clock - ts).total_seconds()))


def check_translate_stall(
    job: dict[str, Any], *, now: datetime | None = None
) -> str | None:
    """Return stall reason enum or None.

    Conditions: stage=translate, not done/error/cancel, idle >= stall_sec.
    Never kill a live worker: ``_local_running`` or unexpired lease means Gemini
    may simply be slow on a long paper (ops showed false translate_stalled).
    """
    if not ingest_stall_detector_enabled():
        return None
    if not isinstance(job, dict):
        return None
    if job.get("done") or job.get("error") or job.get("_discarded"):
        return None
    if job.get("cancel_requested"):
        return None
    if job.get("_local_running"):
        # design/169d — sample so agents see false-stall skips.
        try:
            import random

            if random.randint(1, 20) == 1:
                from sentence_reading.llm import evidence_bus as eb

                eb.emit(
                    "stall_skipped_live_worker",
                    severity="sample",
                    job_id=str(job.get("job_id") or ""),
                    cache_id=str(job.get("cache_id") or job.get("target_cache_id") or ""),
                    owner_uid=str(job.get("owner_uid") or ""),
                    stage="translate",
                    percent=int(job.get("percent") or 0),
                    details={"reason": "local_running"},
                    ok=True,
                    code="stall_skipped_live_worker",
                )
        except Exception:  # noqa: BLE001
            pass
        return None
    try:
        from sentence_reading.llm.ingest_jobs_gcs import lease_expired

        if not lease_expired(job, now=now):
            try:
                import random

                if random.randint(1, 20) == 1:
                    from sentence_reading.llm import evidence_bus as eb

                    eb.emit(
                        "stall_skipped_live_worker",
                        severity="sample",
                        cache_id=str(job.get("cache_id") or job.get("target_cache_id") or ""),
                        owner_uid=str(job.get("owner_uid") or ""),
                        stage="translate",
                        percent=int(job.get("percent") or 0),
                        details={"reason": "lease_alive"},
                        ok=True,
                        code="stall_skipped_live_worker",
                    )
            except Exception:  # noqa: BLE001
                pass
            return None
    except Exception:  # noqa: BLE001
        # EDGE: if lease helpers fail, fall through to idle check only.
        pass
    if str(job.get("stage") or "").strip().lower() != "translate":
        return None
    idle = progress_idle_sec(job, now=now)
    if idle is None:
        return None
    limit = translate_stall_sec()
    if idle < limit:
        return None
    return "translate_idle"


def sweep_candidate(
    job: dict[str, Any], *, now: datetime | None = None
) -> str:
    """Return none | reclaim | mark_lost for sweeper.

    - local running → none
    - done/error/cancel → none
    - lease not expired → none (or translate stall → mark_lost via stall path)
    - lease expired → reclaim first; caller marks lost if reclaim fails
    """
    if not isinstance(job, dict):
        return "none"
    if job.get("done") or job.get("error") or job.get("_discarded"):
        return "none"
    if job.get("cancel_requested"):
        return "none"
    if job.get("_local_running"):
        return "none"
    from sentence_reading.llm.ingest_jobs_gcs import lease_expired

    if not lease_expired(job, now=now):
        return "none"
    return "reclaim"
