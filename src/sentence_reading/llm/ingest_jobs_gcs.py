"""
Durable ingest job records under users/{uid}/ingest_jobs/ (design/71).

WHY: Cloud Run jobs lived only in process memory — poll on another instance → 404.
EDGE: path-safe job_id only; personal_object_name scopes by session UID (no body user_id).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
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


def ingest_jobs_gcs_enabled() -> bool:
    return bool(gcs_config().enabled)


def valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.match((job_id or "").strip()))


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


def serialize_job_record(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Persistable snapshot — no temp paths, no raw PDF."""
    result = job.get("result")
    return {
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
    }


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


def should_push_job(job: dict[str, Any], *, force: bool = False) -> bool:
    """Throttle GCS writes — stage change, +5% jump, or terminal."""
    if force or job.get("done") or job.get("error"):
        return True
    prev_p = int(job.get("_gcs_pushed_percent") or -1)
    prev_s = str(job.get("_gcs_pushed_stage") or "")
    cur_p = int(job.get("percent") or 0)
    cur_s = str(job.get("stage") or "")
    if cur_s != prev_s:
        return True
    if cur_p - prev_p >= 5:
        return True
    return False


def safe_filename(name: str) -> str:
    raw = (name or "").strip()[:180]
    if _SAFE_NAME.match(raw):
        return raw
    # EDGE: keep extension if present, scrub the rest.
    return re.sub(r"[^\w.\-]+", "_", raw)[:180] or "document.pdf"
