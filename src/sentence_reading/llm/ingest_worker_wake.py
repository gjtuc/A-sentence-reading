# -*- coding: utf-8 -*-
"""design/173c + design/178 — wake external ingest worker (HTTP) with causal evidence."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from sentence_reading.llm.ingest_jobs_gcs import (
    ingest_inline_enabled,
    ingest_worker_configured,
    ingest_worker_secret,
    ingest_worker_url,
)

log = logging.getLogger(__name__)

_WAKE_PATHS = frozenset({"spawn", "reclaim", "status_probe", "manual"})
_MISMATCH_THROTTLE_S = 60.0
_last_mismatch_emit_mono = 0.0


@dataclass(frozen=True)
class WakeResult:
    """design/178 — structured wake outcome (never bool-only in evidence)."""

    ok: bool
    outcome: str
    elapsed_ms: int = 0
    has_url: bool = False
    has_secret: bool = False
    configured: bool = False
    http_status: int | None = None
    exc_class: str = ""
    response_ok: bool | None = None
    wake_path: str = "spawn"

    def details(self) -> dict[str, Any]:
        """_safe_details-legal dict for evidence/ops."""
        out: dict[str, Any] = {
            "wake_outcome": _snake(self.outcome) or "exception",
            "wake_path": _snake(self.wake_path) or "spawn",
            "elapsed_ms": int(self.elapsed_ms),
            "has_url": bool(self.has_url),
            "has_secret": bool(self.has_secret),
            "configured": bool(self.configured),
            "ingest_inline": 1 if ingest_inline_enabled() else 0,
        }
        if self.http_status is not None:
            out["wake_http_status"] = int(self.http_status)
        if self.exc_class:
            out["exc_class"] = _snake(self.exc_class) or "exception"
        if self.response_ok is not None:
            out["response_ok"] = bool(self.response_ok)
        return out


def _snake(raw: str) -> str:
    s = str(raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or not re.match(r"^[a-z][a-z0-9_]{0,63}$", s):
        return ""
    return s[:64]


def _exc_class_token(exc: BaseException) -> str:
    name = type(exc).__name__
    # CamelCase → snake
    spaced = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced)
    return _snake(spaced) or "exception"


def _flags() -> tuple[bool, bool, bool]:
    has_url = bool(ingest_worker_url())
    has_secret = bool(ingest_worker_secret())
    return has_url, has_secret, has_url and has_secret


def capacity_profile_token() -> str:
    raw = (os.environ.get("ASR_CAPACITY_PROFILE") or "").strip()
    return _snake(raw.replace("-", "_")) or ""


def emit_worker_config_mismatch(
    *,
    wake_path: str = "status",
    job_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    force: bool = False,
) -> bool:
    """
    design/178 — emit when inline=0 but worker URL/secret missing.
    Returns True if emitted. Throttled on status_probe unless force.
    """
    global _last_mismatch_emit_mono
    if ingest_inline_enabled() or ingest_worker_configured():
        return False
    path = _snake(wake_path) or "status"
    if path == "status_probe" and not force:
        now = time.monotonic()
        if now - _last_mismatch_emit_mono < _MISMATCH_THROTTLE_S:
            return False
        _last_mismatch_emit_mono = now
    has_url, has_secret, _cfg = _flags()
    try:
        from sentence_reading.llm import evidence_bus as eb

        det: dict[str, Any] = {
            "ingest_inline": 0,
            "has_url": has_url,
            "has_secret": has_secret,
            "configured": False,
            "wake_path": path,
            "mismatch_kind": "inline_off_worker_unset",
        }
        cp = capacity_profile_token()
        if cp:
            det["capacity_profile"] = cp
        eb.emit(
            "worker_config_mismatch",
            severity="error",
            job_id=job_id,
            owner_uid=owner_uid,
            trace_id=trace_id,
            stage="worker_config",
            details=det,
            ok=False,
            code="worker_config_mismatch",
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _emit_wake(
    kind: str,
    *,
    job_id: str,
    owner_uid: str,
    trace_id: str,
    details: dict[str, Any],
    ok: bool | None = None,
    http_status: int | None = None,
    severity: str = "boundary",
) -> None:
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            kind,
            severity=severity,
            job_id=job_id,
            owner_uid=owner_uid,
            trace_id=trace_id,
            stage="worker_wake",
            details=details,
            ok=ok,
            http_status=http_status,
            code=kind,
        )
    except Exception:  # noqa: BLE001
        pass


async def wake_ingest_worker(
    job_id: str,
    owner_uid: str,
    *,
    wake_path: str = "spawn",
    trace_id: str = "",
    emit: bool = True,
) -> WakeResult:
    """
    POST /internal/run-job on worker service.
    Fail-soft: outcome != ok when not configured or network error (job stays queued).
    design/178 — always returns WakeResult; emits start/done when emit=True.
    """
    jid = (job_id or "").strip()
    uid = (owner_uid or "").strip()
    path = _snake(wake_path) or "spawn"
    if path not in _WAKE_PATHS:
        path = "spawn"
    has_url, has_secret, configured = _flags()
    t0 = time.perf_counter()

    def _ms() -> int:
        return max(0, int((time.perf_counter() - t0) * 1000))

    if emit:
        _emit_wake(
            "worker_wake_start",
            job_id=jid,
            owner_uid=uid,
            trace_id=trace_id,
            details={
                "wake_path": path,
                "configured": configured,
                "has_url": has_url,
                "has_secret": has_secret,
                "ingest_inline": 1 if ingest_inline_enabled() else 0,
            },
            ok=None,
        )

    if not jid or not uid:
        result = WakeResult(
            ok=False,
            outcome="missing_ids",
            elapsed_ms=_ms(),
            has_url=has_url,
            has_secret=has_secret,
            configured=configured,
            wake_path=path,
        )
        if emit:
            _emit_wake(
                "worker_wake_done",
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                details=result.details(),
                ok=False,
                severity="error",
            )
        return result

    if not configured:
        if emit:
            emit_worker_config_mismatch(
                wake_path=path,
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                force=True,
            )
        result = WakeResult(
            ok=False,
            outcome="not_configured",
            elapsed_ms=_ms(),
            has_url=has_url,
            has_secret=has_secret,
            configured=False,
            wake_path=path,
        )
        if emit:
            _emit_wake(
                "worker_wake_done",
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                details=result.details(),
                ok=False,
                severity="error",
            )
        log.debug("ingest worker wake skip: not configured")
        return result

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
            result = WakeResult(
                ok=False,
                outcome="http_error",
                elapsed_ms=_ms(),
                has_url=has_url,
                has_secret=has_secret,
                configured=True,
                http_status=int(resp.status_code),
                wake_path=path,
            )
            if emit:
                _emit_wake(
                    "worker_wake_done",
                    job_id=jid,
                    owner_uid=uid,
                    trace_id=trace_id,
                    details=result.details(),
                    ok=False,
                    http_status=result.http_status,
                    severity="error",
                )
            return result
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            result = WakeResult(
                ok=False,
                outcome="json_error",
                elapsed_ms=_ms(),
                has_url=has_url,
                has_secret=has_secret,
                configured=True,
                http_status=200,
                exc_class=_exc_class_token(exc),
                wake_path=path,
            )
            if emit:
                _emit_wake(
                    "worker_wake_done",
                    job_id=jid,
                    owner_uid=uid,
                    trace_id=trace_id,
                    details=result.details(),
                    ok=False,
                    http_status=200,
                    severity="error",
                )
            return result
        resp_ok = bool(data.get("ok")) if isinstance(data, dict) else False
        if not resp_ok:
            result = WakeResult(
                ok=False,
                outcome="ok_false",
                elapsed_ms=_ms(),
                has_url=has_url,
                has_secret=has_secret,
                configured=True,
                http_status=200,
                response_ok=False,
                wake_path=path,
            )
            if emit:
                _emit_wake(
                    "worker_wake_done",
                    job_id=jid,
                    owner_uid=uid,
                    trace_id=trace_id,
                    details=result.details(),
                    ok=False,
                    http_status=200,
                    severity="error",
                )
            return result
        result = WakeResult(
            ok=True,
            outcome="ok",
            elapsed_ms=_ms(),
            has_url=has_url,
            has_secret=has_secret,
            configured=True,
            http_status=200,
            response_ok=True,
            wake_path=path,
        )
        if emit:
            _emit_wake(
                "worker_wake_done",
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                details=result.details(),
                ok=True,
                http_status=200,
            )
        return result
    except httpx.TimeoutException as exc:
        log.warning("ingest worker wake timeout job=%s: %s", jid[:20], exc)
        result = WakeResult(
            ok=False,
            outcome="timeout",
            elapsed_ms=_ms(),
            has_url=has_url,
            has_secret=has_secret,
            configured=True,
            exc_class=_exc_class_token(exc),
            wake_path=path,
        )
        if emit:
            _emit_wake(
                "worker_wake_done",
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                details=result.details(),
                ok=False,
                severity="error",
            )
        return result
    except httpx.TransportError as exc:
        log.warning("ingest worker wake connect job=%s: %s", jid[:20], exc)
        result = WakeResult(
            ok=False,
            outcome="connect_error",
            elapsed_ms=_ms(),
            has_url=has_url,
            has_secret=has_secret,
            configured=True,
            exc_class=_exc_class_token(exc),
            wake_path=path,
        )
        if emit:
            _emit_wake(
                "worker_wake_done",
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                details=result.details(),
                ok=False,
                severity="error",
            )
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("ingest worker wake failed job=%s: %s", jid[:20], exc)
        result = WakeResult(
            ok=False,
            outcome="exception",
            elapsed_ms=_ms(),
            has_url=has_url,
            has_secret=has_secret,
            configured=True,
            exc_class=_exc_class_token(exc),
            wake_path=path,
        )
        if emit:
            _emit_wake(
                "worker_wake_done",
                job_id=jid,
                owner_uid=uid,
                trace_id=trace_id,
                details=result.details(),
                ok=False,
                severity="error",
            )
        return result


def stash_wake_on_job(job: dict[str, Any] | None, result: WakeResult) -> None:
    """Persist last wake fields on in-memory job for terminal join."""
    if not isinstance(job, dict):
        return
    job["_last_wake_outcome"] = result.outcome[:64]
    job["_last_wake_path"] = result.wake_path[:32]
    job["_last_wake_elapsed_ms"] = int(result.elapsed_ms)
    job["_last_wake_configured"] = bool(result.configured)
    job["_last_wake_has_url"] = bool(result.has_url)
    job["_last_wake_has_secret"] = bool(result.has_secret)
    if result.http_status is not None:
        job["_last_wake_http_status"] = int(result.http_status)
    else:
        job.pop("_last_wake_http_status", None)
    if result.exc_class:
        job["_last_wake_exc_class"] = result.exc_class[:64]
    else:
        job.pop("_last_wake_exc_class", None)


def wake_fields_from_job(job: dict[str, Any] | None) -> dict[str, Any]:
    """Extract stashed wake fields for terminal/sweep details."""
    if not isinstance(job, dict):
        return {}
    out: dict[str, Any] = {}
    outcome = _snake(str(job.get("_last_wake_outcome") or ""))
    if outcome:
        out["wake_outcome"] = outcome
    path = _snake(str(job.get("_last_wake_path") or ""))
    if path:
        out["wake_path"] = path
    if "_last_wake_elapsed_ms" in job:
        try:
            out["wake_elapsed_ms"] = int(job["_last_wake_elapsed_ms"])
        except (TypeError, ValueError):
            pass
    if "_last_wake_http_status" in job:
        try:
            out["wake_http_status"] = int(job["_last_wake_http_status"])
        except (TypeError, ValueError):
            pass
    if "_last_wake_configured" in job:
        out["wake_configured"] = bool(job["_last_wake_configured"])
    if "_last_wake_has_url" in job:
        out["wake_has_url"] = bool(job["_last_wake_has_url"])
    if "_last_wake_has_secret" in job:
        out["wake_has_secret"] = bool(job["_last_wake_has_secret"])
    exc = _snake(str(job.get("_last_wake_exc_class") or ""))
    if exc:
        out["wake_exc_class"] = exc
    return out
