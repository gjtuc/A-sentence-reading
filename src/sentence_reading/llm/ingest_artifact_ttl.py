"""design/184 — TTL purge for ingest intermediate GCS artifacts (not papers/)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

_JOB_FILE_RE = re.compile(r"^([a-zA-Z0-9]{8,32})\.json$")
_UPLOAD_FILE_RE = re.compile(r"^([a-zA-Z0-9]{8,32})\.(pdf|docx)$", re.I)
_UID_SEG_RE = re.compile(r"^[a-zA-Z0-9_\-]{6,128}$")

_ALLOWED_ARTIFACT_ROOTS = frozenset(
    {"ingest_jobs", "ingest_uploads", "ingest_payloads"}
)


def artifact_ttl_enabled() -> bool:
    v = (os.environ.get("ASR_INGEST_ARTIFACT_TTL") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def artifact_ttl_dry_run() -> bool:
    v = (os.environ.get("ASR_INGEST_ARTIFACT_TTL_DRY_RUN") or "0").strip().lower()
    return v in ("1", "true", "on", "yes")


def terminal_ttl_hours() -> int:
    raw = (os.environ.get("ASR_INGEST_ARTIFACT_TTL_HOURS") or "168").strip()
    try:
        h = int(raw)
    except ValueError:
        return 168
    return max(1, min(h, 24 * 90))


def abandon_hours() -> int:
    raw = (os.environ.get("ASR_INGEST_ARTIFACT_ABANDON_HOURS") or "336").strip()
    try:
        h = int(raw)
    except ValueError:
        return 336
    return max(24, min(h, 24 * 180))


def purge_interval_sec() -> int:
    raw = (os.environ.get("ASR_INGEST_ARTIFACT_PURGE_INTERVAL_S") or "3600").strip()
    try:
        s = int(raw)
    except ValueError:
        return 3600
    return max(300, min(s, 24 * 3600))


def purge_batch_limit() -> int:
    raw = (os.environ.get("ASR_INGEST_ARTIFACT_PURGE_BATCH") or "20").strip()
    try:
        n = int(raw)
    except ValueError:
        return 20
    return max(1, min(n, 100))


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


def _hash16(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def is_terminal_job(job: dict[str, Any]) -> bool:
    if job.get("error"):
        return True
    if job.get("done") is True:
        return True
    phase = str(job.get("ingest_phase") or "").strip().lower()
    return phase in ("error", "complete")


def stamp_terminal_retention(
    job: dict[str, Any], *, now: datetime | None = None
) -> bool:
    """Set artifact_retain_until once when job becomes terminal."""
    if not isinstance(job, dict) or not is_terminal_job(job):
        return False
    if str(job.get("artifact_retain_until") or "").strip():
        return False
    n = now or _utc_now()
    reason = "terminal_error" if job.get("error") else "terminal_ok"
    job["artifact_retain_until"] = (
        n + timedelta(hours=terminal_ttl_hours())
    ).isoformat()
    job["artifact_retain_reason"] = reason
    return True


def clear_retention_on_reclaim(job: dict[str, Any]) -> None:
    if not isinstance(job, dict):
        return
    job.pop("artifact_retain_until", None)
    job.pop("artifact_retain_reason", None)
    job.pop("artifact_purge_partial", None)


def effective_retain_until(job: dict[str, Any]) -> datetime | None:
    explicit = _parse_iso(str(job.get("artifact_retain_until") or ""))
    if explicit is not None:
        return explicit
    if not is_terminal_job(job):
        return None
    base = _parse_iso(str(job.get("updated_at") or "")) or _utc_now()
    return base + timedelta(hours=terminal_ttl_hours())


def should_purge_job(
    job: dict[str, Any],
    *,
    now: datetime | None = None,
    has_upload: bool = False,
) -> tuple[bool, str]:
    from sentence_reading.llm.ingest_jobs_gcs import lease_expired

    n = now or _utc_now()
    if not isinstance(job, dict):
        return False, "bad_job"
    if is_terminal_job(job):
        until = effective_retain_until(job)
        if until is None:
            return False, "no_until"
        if n >= until:
            return True, str(job.get("artifact_retain_reason") or "terminal_ttl")
        return False, "not_yet"
    if not lease_expired(job, now=n):
        return False, "lease_alive"
    if has_upload:
        return False, "reclaim_upload"
    base = _parse_iso(str(job.get("updated_at") or ""))
    if base is not None and n >= base + timedelta(hours=abandon_hours()):
        return True, "abandoned_no_upload"
    return False, "non_terminal"


def assert_deletable_object(object_name: str, *, uid: str) -> str | None:
    name = (object_name or "").strip().replace("\\", "/")
    uid_s = (uid or "").strip()
    if not name or not uid_s or ".." in name:
        return None
    if "/papers/" in name:
        return None
    marker = f"/users/{uid_s}/"
    idx = name.find(marker)
    if idx < 0:
        return None
    rest = name[idx + len(marker) :]
    root = rest.split("/", 1)[0]
    if root not in _ALLOWED_ARTIFACT_ROOTS:
        return None
    return name


def _delete_one(object_name: str, *, uid: str, dry_run: bool) -> str:
    safe = assert_deletable_object(object_name, uid=uid)
    if not safe:
        return "refused"
    if dry_run:
        return "dry_run"
    from sentence_reading.llm.gcs_sync import delete_bytes

    ok = delete_bytes(safe)
    return "deleted" if ok else "missing"


def delete_job_artifacts(
    job_id: str,
    *,
    owner_uid: str,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    from sentence_reading.llm.ingest_jobs_gcs import (
        _with_uid,
        ingest_job_object,
        ingest_payload_object,
        ingest_upload_object,
    )

    uid = (owner_uid or "").strip()
    jid = (job_id or "").strip()
    dry = artifact_ttl_dry_run() if dry_run is None else dry_run
    counts = {
        "upload": 0,
        "payload": 0,
        "job": 0,
        "refused": 0,
        "missing": 0,
        "error": 0,
        "dry_run": 0,
    }
    if not uid or not jid:
        return {"ok": False, "error": "bad_ids", "counts": counts, "dry_run": dry}

    with _with_uid(uid):
        for suffix in (".pdf", ".docx"):
            obj = ingest_upload_object(jid, suffix=suffix, uid=uid)
            if not obj:
                continue
            st = _delete_one(obj, uid=uid, dry_run=dry)
            if st == "deleted":
                counts["upload"] += 1
            elif st in counts:
                counts[st] += 1

        pobj = ingest_payload_object(jid, uid=uid)
        if pobj:
            st = _delete_one(pobj, uid=uid, dry_run=dry)
            if st == "deleted":
                counts["payload"] += 1
            elif st in counts:
                counts[st] += 1

        jobj = ingest_job_object(jid, uid=uid)
        if jobj:
            st = _delete_one(jobj, uid=uid, dry_run=dry)
            if st == "deleted":
                counts["job"] += 1
            elif st in counts:
                counts[st] += 1

    ok = counts["refused"] == 0 and counts["error"] == 0
    return {
        "ok": ok,
        "job_id": jid,
        "owner_uid_hash16": _hash16(uid),
        "dry_run": dry,
        "counts": counts,
    }


def _list_uid_job_ids(uid: str) -> list[str]:
    from sentence_reading.llm.gcs_sync import list_blobs_under, object_name
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid

    with _with_uid(uid):
        prefix = object_name("users", uid, "ingest_jobs")
        if not prefix:
            return []
        names = list_blobs_under(prefix)
    out: list[str] = []
    for n in names:
        base = n.rsplit("/", 1)[-1]
        m = _JOB_FILE_RE.match(base)
        if m:
            out.append(m.group(1))
    return out


def _list_uid_upload_ids(uid: str) -> list[tuple[str, str]]:
    from sentence_reading.llm.gcs_sync import list_blobs_under, object_name
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid

    with _with_uid(uid):
        prefix = object_name("users", uid, "ingest_uploads")
        if not prefix:
            return []
        names = list_blobs_under(prefix)
    out: list[tuple[str, str]] = []
    for n in names:
        if "/papers/" in n:
            continue
        base = n.rsplit("/", 1)[-1]
        m = _UPLOAD_FILE_RE.match(base)
        if m:
            out.append((m.group(1), "." + m.group(2).lower()))
    return out


def _upload_blob_age_hours(uid: str, job_id: str, suffix: str) -> float | None:
    from sentence_reading.llm.gcs_sync import (
        _assert_under_prefix,
        _storage_client,
        gcs_client_ready,
        gcs_config,
    )
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid, ingest_upload_object

    with _with_uid(uid):
        obj = ingest_upload_object(job_id, suffix=suffix, uid=uid)
    if not obj:
        return None
    name = _assert_under_prefix(obj)
    if not name or "/papers/" in name:
        return None
    ready, _ = gcs_client_ready()
    if not ready:
        return None
    try:
        cfg = gcs_config()
        blob = _storage_client().bucket(cfg.bucket).blob(name)
        blob.reload()
        created = getattr(blob, "time_created", None)
        if created is None:
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (_utc_now() - created.astimezone(timezone.utc)).total_seconds() / 3600.0
        return float(age)
    except Exception:  # noqa: BLE001
        return None


def discover_owner_uids() -> list[str]:
    uids: set[str] = set()
    try:
        from sentence_reading.llm.auth_accounts import accounts_path

        raw = json.loads(accounts_path().read_text(encoding="utf-8"))
        users = raw.get("users") if isinstance(raw, dict) else None
        if isinstance(users, list):
            for u in users:
                if isinstance(u, dict):
                    uid = str(u.get("uid") or "").strip()
                    if uid and _UID_SEG_RE.match(uid):
                        uids.add(uid)
    except Exception:  # noqa: BLE001
        pass
    try:
        from sentence_reading.llm.gcs_sync import (
            _storage_client,
            gcs_client_ready,
            gcs_config,
        )

        ready, _ = gcs_client_ready()
        if ready:
            cfg = gcs_config()
            prefix = f"{cfg.prefix}/users/"
            client = _storage_client()
            iterator = client.bucket(cfg.bucket).list_blobs(
                prefix=prefix, delimiter="/"
            )
            for _ in iterator:
                pass
            for p in getattr(iterator, "prefixes", []) or []:
                segs = str(p).rstrip("/").split("/")
                if len(segs) >= 3 and segs[-2] == "users":
                    uid = segs[-1]
                    if uid and _UID_SEG_RE.match(uid):
                        uids.add(uid)
    except Exception:  # noqa: BLE001
        log.debug("uid discovery gcs skip", exc_info=True)
    return sorted(uids)


def purge_uid(
    uid: str, *, limit: int | None = None, now: datetime | None = None
) -> dict[str, Any]:
    from sentence_reading.llm.ingest_jobs_gcs import (
        _with_uid,
        ingest_upload_object,
        load_ingest_job,
        load_ingest_upload,
    )

    uid = (uid or "").strip()
    n = now or _utc_now()
    lim = purge_batch_limit() if limit is None else max(1, min(int(limit), 100))
    summary: dict[str, Any] = {
        "uid_hash16": _hash16(uid),
        "examined": 0,
        "purged_jobs": 0,
        "orphan_uploads": 0,
        "skipped": 0,
        "refused": 0,
        "errors": 0,
        "dry_run": artifact_ttl_dry_run(),
        "actions": [],
    }
    if not uid or not artifact_ttl_enabled():
        return summary

    job_ids = _list_uid_job_ids(uid)
    uploads = _list_uid_upload_ids(uid)
    upload_set = {j for j, _ in uploads}

    purged = 0
    for jid in job_ids:
        if purged >= lim:
            break
        summary["examined"] += 1
        job = load_ingest_job(jid, owner_uid=uid)
        if job is None:
            summary["skipped"] += 1
            continue
        has_upload = jid in upload_set or any(
            load_ingest_upload(jid, owner_uid=uid, suffix=s) is not None
            for s in (".pdf", ".docx")
        )
        ok_purge, reason = should_purge_job(job, now=n, has_upload=has_upload)
        if not ok_purge:
            summary["skipped"] += 1
            continue
        result = delete_job_artifacts(jid, owner_uid=uid)
        if result.get("counts", {}).get("refused", 0):
            summary["refused"] += 1
        if result.get("counts", {}).get("error", 0):
            summary["errors"] += 1
        if result.get("ok") or result.get("dry_run"):
            summary["purged_jobs"] += 1
            purged += 1
            summary["actions"].append(
                {
                    "job_id_hash16": _hash16(jid),
                    "reason": reason,
                    "counts": result.get("counts"),
                }
            )
            try:
                from sentence_reading.llm import evidence_bus as eb

                eb.emit(
                    "ingest_artifact_deleted",
                    ok=bool(result.get("ok")),
                    code=reason,
                    details={
                        "job_id_hash16": _hash16(jid),
                        "uid_hash16": _hash16(uid),
                        "dry_run": bool(result.get("dry_run")),
                        "counts": result.get("counts") or {},
                    },
                )
            except Exception:  # noqa: BLE001
                pass

    for jid, suffix in uploads:
        if purged >= lim:
            break
        if load_ingest_job(jid, owner_uid=uid) is not None:
            continue
        age = _upload_blob_age_hours(uid, jid, suffix)
        if age is None or age < float(abandon_hours()):
            summary["skipped"] += 1
            continue
        with _with_uid(uid):
            obj = ingest_upload_object(jid, suffix=suffix, uid=uid)
        if not obj:
            continue
        st = _delete_one(obj, uid=uid, dry_run=artifact_ttl_dry_run())
        if st in ("deleted", "dry_run"):
            summary["orphan_uploads"] += 1
            purged += 1
            summary["actions"].append(
                {
                    "job_id_hash16": _hash16(jid),
                    "reason": "orphan_upload",
                    "status": st,
                }
            )
        elif st == "refused":
            summary["refused"] += 1
        elif st == "error":
            summary["errors"] += 1

    return summary


def purge_all_uids(*, limit_total: int | None = None) -> dict[str, Any]:
    lim = purge_batch_limit() if limit_total is None else max(1, int(limit_total))
    uids = discover_owner_uids()
    out: dict[str, Any] = {
        "uid_n": len(uids),
        "purged_jobs": 0,
        "orphan_uploads": 0,
        "refused": 0,
        "errors": 0,
        "dry_run": artifact_ttl_dry_run(),
        "per_uid": [],
    }
    remaining = lim
    for uid in uids:
        if remaining <= 0:
            break
        part = purge_uid(uid, limit=remaining)
        out["purged_jobs"] += int(part.get("purged_jobs") or 0)
        out["orphan_uploads"] += int(part.get("orphan_uploads") or 0)
        out["refused"] += int(part.get("refused") or 0)
        out["errors"] += int(part.get("errors") or 0)
        used = int(part.get("purged_jobs") or 0) + int(
            part.get("orphan_uploads") or 0
        )
        remaining -= used
        out["per_uid"].append(
            {
                "uid_hash16": part.get("uid_hash16"),
                "purged_jobs": part.get("purged_jobs"),
                "orphan_uploads": part.get("orphan_uploads"),
            }
        )
    return out
