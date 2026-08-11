"""
Durable ingest job records under users/{uid}/ingest_jobs/ (design/71).

WHY: Cloud Run jobs lived only in process memory — poll on another instance → 404.
EDGE: path-safe job_id only; personal_object_name scopes by session UID (no body user_id).
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sentence_reading.llm.auth_google import current_gcs_uid, set_gcs_uid
from sentence_reading.llm.gcs_sync import (
    delete_bytes,
    download_bytes,
    gcs_config,
    personal_object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

# Same shape as app-minted ids: job_ + 12 hex chars.
_JOB_ID_RE = re.compile(r"^job_[a-f0-9]{12}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._\- ]{1,180}$")

# design/107 — worker must refresh before this TTL or another instance may reclaim.
_LEASE_TTL_S = 90
_HEARTBEAT_INTERVAL_S = 25

# design/110 — checkpoint envelope (mid-stage skip comes later; TTL ≠ lease).
_CHECKPOINT_SCHEMA_V = 1
_CHECKPOINT_TTL_HOURS_DEFAULT = 168  # 7 days — product: stale → discard


def ingest_jobs_gcs_enabled() -> bool:
    return bool(gcs_config().enabled)


def ingest_job_reclaim_enabled() -> bool:
    """Kill switch: ASR_INGEST_JOB_RECLAIM=0 disables cross-instance restart."""
    raw = (os.environ.get("ASR_INGEST_JOB_RECLAIM") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def ingest_checkpoint_enabled() -> bool:
    """Kill switch: ASR_INGEST_CHECKPOINT=0 disables envelope write/accept."""
    raw = (os.environ.get("ASR_INGEST_CHECKPOINT") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def ingest_resume_skip_enabled() -> bool:
    """Kill switch: ASR_INGEST_RESUME_SKIP=0 disables payload skip (full restart)."""
    if not ingest_checkpoint_enabled():
        return False
    raw = (os.environ.get("ASR_INGEST_RESUME_SKIP") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def lease_ttl_seconds() -> int:
    return _LEASE_TTL_S


def heartbeat_interval_seconds() -> int:
    return _HEARTBEAT_INTERVAL_S


def checkpoint_schema_version() -> int:
    return _CHECKPOINT_SCHEMA_V


def checkpoint_ttl_hours() -> int:
    raw = (os.environ.get("ASR_INGEST_CHECKPOINT_TTL_HOURS") or "").strip()
    if not raw:
        return _CHECKPOINT_TTL_HOURS_DEFAULT
    try:
        hours = int(raw)
    except ValueError:
        return _CHECKPOINT_TTL_HOURS_DEFAULT
    # EDGE: refuse non-positive / absurd values — fail-closed to default.
    if hours < 1 or hours > 24 * 90:
        return _CHECKPOINT_TTL_HOURS_DEFAULT
    return hours


def valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.match((job_id or "").strip()))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    raw = (ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def lease_expired(job: dict[str, Any], *, now: datetime | None = None) -> bool:
    """True when no lease or lease_until is in the past — safe for another worker."""
    until = _parse_iso(str(job.get("lease_until") or ""))
    if until is None:
        # WHY: legacy jobs without lease look abandoned once reclaim is on.
        return True
    clock = now or _utc_now()
    return until <= clock


def stamp_lease(job: dict[str, Any], *, token: str | None = None) -> str:
    """Set lease_until / lease_token on the in-memory job. Returns token."""
    tok = (token or "").strip() or uuid.uuid4().hex[:16]
    job["lease_token"] = tok
    job["lease_until"] = (
        _utc_now() + timedelta(seconds=_LEASE_TTL_S)
    ).isoformat()
    return tok


def _with_uid(uid: str | None):
    """Temporarily bind GCS personal path when background task uid was reset."""

    class _Ctx:
        def __enter__(self):
            self._prev = current_gcs_uid()
            if uid:
                set_gcs_uid(uid)
            return self

        def __exit__(self, *args):
            set_gcs_uid(self._prev)

    return _Ctx()


def ingest_job_object(job_id: str, *, uid: str | None = None) -> str | None:
    jid = (job_id or "").strip()
    if not valid_job_id(jid):
        return None
    with _with_uid(uid):
        return personal_object_name("ingest_jobs", f"{jid}.json")


def ingest_upload_object(
    job_id: str, *, suffix: str = ".pdf", uid: str | None = None
) -> str | None:
    jid = (job_id or "").strip()
    if not valid_job_id(jid):
        return None
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    # WHY: only allow short safe extensions used by ingest.
    if ext.lower() not in (".pdf", ".docx"):
        return None
    with _with_uid(uid):
        return personal_object_name("ingest_uploads", f"{jid}{ext.lower()}")


def public_job_view(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Shape returned by GET /api/ingest/jobs/{id} (no owner_uid leak beyond need)."""
    out: dict[str, Any] = {
        "ok": True,
        "job_id": job_id,
        "percent": int(job.get("percent") or 0),
        "stage": str(job.get("stage") or ""),
        "message": str(job.get("message") or ""),
        "done": bool(job.get("done")),
    }
    if job.get("content_hash"):
        out["content_hash"] = str(job["content_hash"])
    # design/110 — resume hint only (stage/cursor); never paper text.
    cp = job.get("checkpoint")
    if isinstance(cp, dict) and cp.get("stage"):
        out["checkpoint_stage"] = str(cp.get("stage") or "")[:40]
        cursor = cp.get("cursor")
        if isinstance(cursor, dict):
            try:
                done = int(cursor.get("done") or 0)
                total = int(cursor.get("total") or 0)
            except (TypeError, ValueError):
                done, total = 0, 0
            if total > 0:
                out["checkpoint_cursor"] = {"done": done, "total": total}
    if job.get("error"):
        out["ok"] = False
        out["error"] = "ingest_failed"
        out["message"] = str(job["error"])
        out["done"] = True
        return out
    if job.get("done") and isinstance(job.get("result"), dict):
        out.update(job["result"])
        out["percent"] = 100
        out["done"] = True
        out["translate_pending"] = False
    elif isinstance(job.get("result"), dict):
        out.update(job["result"])
        out["done"] = False
        out["translate_pending"] = True
    return out


def build_checkpoint(
    *,
    stage: str,
    content_hash: str,
    pipeline_version: str,
    cursor: dict[str, Any] | None = None,
    now: datetime | None = None,
    payload_ref: str | None = None,
) -> dict[str, Any]:
    """Minimal resume envelope — no paper body, no titles."""
    clock = now or _utc_now()
    out: dict[str, Any] = {
        "v": _CHECKPOINT_SCHEMA_V,
        "pipeline_version": str(pipeline_version or "").strip()[:32],
        "stage": str(stage or "").strip()[:40],
        "content_hash": str(content_hash or "").strip().lower()[:64],
        "updated_at": clock.isoformat(),
    }
    if isinstance(cursor, dict):
        try:
            done = int(cursor.get("done") or 0)
            total = int(cursor.get("total") or 0)
        except (TypeError, ValueError):
            done, total = 0, 0
        # EDGE: clamp absurd cursors — never trust unbounded client-like values.
        done = max(0, min(done, 1_000_000))
        total = max(0, min(total, 1_000_000))
        if total > 0:
            out["cursor"] = {"done": done, "total": total}
    # design/112 — relative key only (job_*.json); never absolute path.
    pref = str(payload_ref or "").strip()[:80]
    if pref and ".." not in pref and "/" not in pref and "\\" not in pref:
        out["payload_ref"] = pref
    return out


def checkpoint_is_valid(
    checkpoint: Any,
    *,
    content_hash: str,
    pipeline_version: str,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """
    Accept/discard gate for design/110.
    Returns (ok, reason). reason is machine-short for logs/tests — not user email.
    """
    if not ingest_checkpoint_enabled():
        return False, "disabled"
    if not isinstance(checkpoint, dict):
        return False, "missing"
    try:
        ver = int(checkpoint.get("v") or 0)
    except (TypeError, ValueError):
        return False, "schema"
    if ver != _CHECKPOINT_SCHEMA_V:
        return False, "schema"
    if str(checkpoint.get("pipeline_version") or "") != str(pipeline_version or ""):
        return False, "pipeline"
    cp_hash = str(checkpoint.get("content_hash") or "").strip().lower()
    expect = str(content_hash or "").strip().lower()
    if not expect or cp_hash != expect:
        return False, "hash"
    updated = _parse_iso(str(checkpoint.get("updated_at") or ""))
    if updated is None:
        return False, "ttl"
    clock = now or _utc_now()
    age = clock - updated
    if age.total_seconds() > checkpoint_ttl_hours() * 3600:
        return False, "ttl"
    if age.total_seconds() < -300:
        # EDGE: clock skew far in the future → discard (fail-closed).
        return False, "ttl"
    stage = str(checkpoint.get("stage") or "").strip()
    if not stage or stage in ("done", "error", "queued"):
        return False, "stage"
    return True, "ok"


def checkpoint_resume_message(checkpoint: dict[str, Any]) -> str:
    """Human poll message: where we *intend* to resume (skip wired later)."""
    stage = str(checkpoint.get("stage") or "").strip()
    labels = {
        "extract": "추출",
        "cache": "보관본",
        "quality": "품질",
        "vision": "비전",
        "figures": "그림",
        "debone": "다듬기",
        "split": "문장 나누기",
        "ready": "읽기 준비",
        "translate": "번역",
        "save": "저장",
        "shadowing_chunks": "연습 구간",
    }
    label = labels.get(stage, stage or "처리")
    cursor = checkpoint.get("cursor")
    if isinstance(cursor, dict):
        try:
            done = int(cursor.get("done") or 0)
            total = int(cursor.get("total") or 0)
        except (TypeError, ValueError):
            done, total = 0, 0
        if total > 0:
            return f"이어받을 지점 유지 · {label} {done}/{total}"
    return f"이어받을 지점 유지 · {label}"


def stamp_checkpoint_on_job(
    job: dict[str, Any],
    *,
    pipeline_version: str,
    cursor: dict[str, Any] | None = None,
) -> None:
    """Update in-memory checkpoint when progress advances (design/110·112)."""
    if not ingest_checkpoint_enabled():
        job.pop("checkpoint", None)
        return
    if job.get("done") or job.get("error"):
        return
    stage = str(job.get("stage") or "").strip()
    if not stage or stage in ("done", "error"):
        return
    prev = job.get("checkpoint") if isinstance(job.get("checkpoint"), dict) else {}
    job["checkpoint"] = build_checkpoint(
        stage=stage,
        content_hash=str(job.get("content_hash") or ""),
        pipeline_version=pipeline_version,
        cursor=cursor,
        payload_ref=str((prev or {}).get("payload_ref") or "") or None,
    )


def stage_percent_floor(stage: str) -> int:
    """Progress floor so resume UI does not reset to extract 5%."""
    floors = {
        "extract": 5,
        "cache": 10,
        "quality": 12,
        "vision": 20,
        "figures": 42,
        "debone": 48,
        "split": 70,
        "ready": 88,
        "translate": 90,
        "save": 98,
        "shadowing_chunks": 99,
    }
    return int(floors.get(str(stage or "").strip(), 1))


def ingest_payload_object(job_id: str, *, uid: str | None = None) -> str | None:
    jid = (job_id or "").strip()
    if not valid_job_id(jid):
        return None
    with _with_uid(uid):
        return personal_object_name("ingest_payloads", f"{jid}.json")


def save_ingest_payload(
    job_id: str, payload: dict[str, Any], *, owner_uid: str
) -> bool:
    """Persist mid-stage artifacts under the owner kan (design/112)."""
    if not ingest_jobs_gcs_enabled() or not ingest_resume_skip_enabled():
        return False
    uid = (owner_uid or "").strip()
    if not uid or not isinstance(payload, dict):
        return False
    obj = ingest_payload_object(job_id, uid=uid)
    if not obj:
        return False
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    # EDGE: refuse oversized payloads (fail-closed → full restart later).
    if len(raw) > 8 * 1024 * 1024:
        return False
    return upload_bytes(obj, raw, content_type="application/json")


def load_ingest_payload(
    job_id: str, *, owner_uid: str
) -> dict[str, Any] | None:
    """Load payload for verified uid. Wrong/missing → None."""
    if not ingest_jobs_gcs_enabled() or not ingest_resume_skip_enabled():
        return None
    uid = (owner_uid or "").strip()
    if not uid or not valid_job_id(job_id):
        return None
    obj = ingest_payload_object(job_id, uid=uid)
    if not obj:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("owner_uid") or "") != uid:
        return None
    if str(data.get("job_id") or "") != job_id:
        return None
    return data


def delete_ingest_payload(job_id: str, *, owner_uid: str) -> bool:
    uid = (owner_uid or "").strip()
    obj = ingest_payload_object(job_id, uid=uid)
    if not obj:
        return False
    return delete_bytes(obj)


def payload_is_valid(
    payload: Any,
    *,
    content_hash: str,
    pipeline_version: str,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Accept/discard gate for design/112 payloads."""
    if not ingest_resume_skip_enabled():
        return False, "disabled"
    if not isinstance(payload, dict):
        return False, "missing"
    try:
        ver = int(payload.get("v") or 0)
    except (TypeError, ValueError):
        return False, "schema"
    if ver != _CHECKPOINT_SCHEMA_V:
        return False, "schema"
    if str(payload.get("pipeline_version") or "") != str(pipeline_version or ""):
        return False, "pipeline"
    p_hash = str(payload.get("content_hash") or "").strip().lower()
    expect = str(content_hash or "").strip().lower()
    if not expect or p_hash != expect:
        return False, "hash"
    updated = _parse_iso(str(payload.get("updated_at") or ""))
    if updated is None:
        return False, "ttl"
    clock = now or _utc_now()
    age = clock - updated
    if age.total_seconds() > checkpoint_ttl_hours() * 3600:
        return False, "ttl"
    if age.total_seconds() < -300:
        return False, "ttl"
    completed = str(payload.get("completed") or "").strip()
    if completed not in {
        "vision",
        "vision_partial",
        "debone",
        "ready",
        "translate",
    }:
        return False, "stage"
    return True, "ok"


def serialize_job_record(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Persistable snapshot — no temp paths, no raw PDF."""
    result = job.get("result")
    out: dict[str, Any] = {
        "job_id": job_id,
        "owner_uid": str(job.get("owner_uid") or ""),
        "percent": int(job.get("percent") or 0),
        "stage": str(job.get("stage") or ""),
        "message": str(job.get("message") or ""),
        "done": bool(job.get("done")),
        "error": job.get("error"),
        "result": result if isinstance(result, dict) else None,
        "content_hash": str(job.get("content_hash") or ""),
        "filename": str(job.get("filename") or "")[:180],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # design/110 — reclaim must keep opt-in flags (defaults lied after GCS round-trip).
        "want_translate": bool(job.get("want_translate", True)),
        "want_shadowing_chunks": bool(job.get("want_shadowing_chunks", False)),
    }
    # design/107 — lease so other instances know a worker is still alive.
    if job.get("lease_until"):
        out["lease_until"] = str(job.get("lease_until"))
    if job.get("lease_token"):
        out["lease_token"] = str(job.get("lease_token"))[:32]
    # design/110 — envelope only (no paper text).
    cp = job.get("checkpoint")
    if isinstance(cp, dict) and cp.get("stage"):
        out["checkpoint"] = {
            "v": int(cp.get("v") or _CHECKPOINT_SCHEMA_V),
            "pipeline_version": str(cp.get("pipeline_version") or "")[:32],
            "stage": str(cp.get("stage") or "")[:40],
            "content_hash": str(cp.get("content_hash") or "")[:64],
            "updated_at": str(cp.get("updated_at") or ""),
        }
        cursor = cp.get("cursor")
        if isinstance(cursor, dict):
            try:
                done = int(cursor.get("done") or 0)
                total = int(cursor.get("total") or 0)
            except (TypeError, ValueError):
                done, total = 0, 0
            if total > 0:
                out["checkpoint"]["cursor"] = {
                    "done": max(0, min(done, 1_000_000)),
                    "total": max(0, min(total, 1_000_000)),
                }
        pref = str(cp.get("payload_ref") or "").strip()[:80]
        if pref and ".." not in pref and "/" not in pref and "\\" not in pref:
            out["checkpoint"]["payload_ref"] = pref
    return out


def save_ingest_job(job_id: str, job: dict[str, Any]) -> bool:
    """Push job JSON to the owner’s GCS kan. Fail-soft → False."""
    if not ingest_jobs_gcs_enabled():
        return False
    owner = str(job.get("owner_uid") or "").strip()
    if not owner:
        # WHY: without owner we cannot place under users/{uid}/ — refuse.
        return False
    obj = ingest_job_object(job_id, uid=owner)
    if not obj:
        return False
    payload = serialize_job_record(job_id, job)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    ok = upload_bytes(obj, raw, content_type="application/json")
    if ok:
        job["_gcs_pushed_percent"] = int(job.get("percent") or 0)
        job["_gcs_pushed_stage"] = str(job.get("stage") or "")
    return ok


def load_ingest_job(job_id: str, *, owner_uid: str) -> dict[str, Any] | None:
    """Load job for a verified session uid. Wrong/missing → None (404)."""
    uid = (owner_uid or "").strip()
    if not uid or not valid_job_id(job_id):
        return None
    if not ingest_jobs_gcs_enabled():
        return None
    obj = ingest_job_object(job_id, uid=uid)
    if not obj:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    # EDGE: never return another user’s job even if object path was wrong.
    if str(data.get("owner_uid") or "") != uid:
        return None
    if str(data.get("job_id") or "") != job_id:
        return None
    return data


def delete_ingest_job(job_id: str, *, owner_uid: str) -> bool:
    uid = (owner_uid or "").strip()
    obj = ingest_job_object(job_id, uid=uid)
    if not obj:
        return False
    return delete_bytes(obj)


def save_ingest_upload(
    job_id: str, data: bytes, *, owner_uid: str, suffix: str = ".pdf"
) -> bool:
    """Keep source bytes until job terminal — foundation for later byte-resume."""
    uid = (owner_uid or "").strip()
    if not uid or not data:
        return False
    obj = ingest_upload_object(job_id, suffix=suffix, uid=uid)
    if not obj:
        return False
    ctype = (
        "application/pdf"
        if suffix.lower().endswith("pdf")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return upload_bytes(obj, bytes(data), content_type=ctype)


def delete_ingest_upload(
    job_id: str, *, owner_uid: str, suffix: str = ".pdf"
) -> bool:
    uid = (owner_uid or "").strip()
    obj = ingest_upload_object(job_id, suffix=suffix, uid=uid)
    if not obj:
        return False
    return delete_bytes(obj)


def load_ingest_upload(
    job_id: str, *, owner_uid: str, suffix: str = ".pdf"
) -> bytes | None:
    """Load source bytes for reclaim (design/107). Missing/wrong owner → None."""
    uid = (owner_uid or "").strip()
    if not uid or not valid_job_id(job_id):
        return None
    if not ingest_jobs_gcs_enabled():
        return None
    obj = ingest_upload_object(job_id, suffix=suffix, uid=uid)
    if not obj:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    return bytes(raw)


def try_claim_lease(job_id: str, *, owner_uid: str) -> str | None:
    """
    Atomically-ish claim an expired lease on GCS.
    Returns lease_token if this caller won; None if still leased or missing.
    WHY: two Cloud Run instances may poll at once — loser must not start a worker.
    """
    if not ingest_job_reclaim_enabled() or not ingest_jobs_gcs_enabled():
        return None
    uid = (owner_uid or "").strip()
    if not uid or not valid_job_id(job_id):
        return None
    current = load_ingest_job(job_id, owner_uid=uid)
    if current is None:
        return None
    if current.get("done") or current.get("error"):
        return None
    if not lease_expired(current):
        return None
    token = stamp_lease(current)
    if not save_ingest_job(job_id, current):
        return None
    # EDGE: re-read — if another writer overwrote our token, we lost.
    again = load_ingest_job(job_id, owner_uid=uid)
    if again is None or str(again.get("lease_token") or "") != token:
        return None
    return token


def should_push_job(job: dict[str, Any], *, force: bool = False) -> bool:
    """Throttle GCS writes — stage change, +1% jump, or terminal.

    design/106: quality bumps 12→16 (+4) must reach other Cloud Run instances;
    the old +5% gate left polls stuck at 12% / 「추출 품질 보는 중」.
    """
    if force or job.get("done") or job.get("error"):
        return True
    prev_p = int(job.get("_gcs_pushed_percent") or -1)
    prev_s = str(job.get("_gcs_pushed_stage") or "")
    cur_p = int(job.get("percent") or 0)
    cur_s = str(job.get("stage") or "")
    if cur_s != prev_s:
        return True
    if cur_p - prev_p >= 1:
        return True
    return False


def safe_filename(name: str) -> str:
    raw = (name or "").strip()[:180]
    if _SAFE_NAME.match(raw):
        return raw
    # EDGE: keep extension if present, scrub the rest.
    return re.sub(r"[^\w.\-]+", "_", raw)[:180] or "document.pdf"
