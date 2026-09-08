"""design/186 — TTL purge for transfer_packs/ only."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)


def purge_enabled() -> bool:
    """TTL purge stays on when ASR_TRANSFER_PACK=0 (J15) unless TTL kill."""
    v = (os.environ.get("ASR_TRANSFER_PACK_TTL") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def purge_dry_run() -> bool:
    v = (os.environ.get("ASR_TRANSFER_PACK_TTL_DRY_RUN") or "0").strip().lower()
    return v in ("1", "true", "on", "yes")


def purge_interval_sec() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_PURGE_INTERVAL_S") or "3600").strip()
    try:
        s = int(raw)
    except ValueError:
        return 3600
    return max(300, min(s, 24 * 3600))


def purge_batch_limit() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_PURGE_BATCH") or "20").strip()
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


def should_purge_meta(meta: dict[str, Any], *, now: datetime | None = None) -> tuple[bool, str]:
    from sentence_reading.llm.transfer_pack_gcs import (
        transfer_pack_abandon_hours,
    )

    n = now or _utc_now()
    if not isinstance(meta, dict):
        return False, "bad_meta"
    lease = _parse_iso(str(meta.get("download_lease_until") or ""))
    if lease is not None and n < lease:
        return False, "lease_alive"
    status = str(meta.get("status") or "")
    if status == "ready":
        exp = _parse_iso(str(meta.get("expires_at") or ""))
        if exp is None:
            return False, "no_expires"
        if n >= exp:
            return True, "ttl_expired"
        return False, "not_yet"
    if status == "pending":
        base = _parse_iso(str(meta.get("updated_at") or meta.get("created_at") or ""))
        if base is None:
            return False, "no_updated"
        if n >= base + timedelta(hours=transfer_pack_abandon_hours()):
            return True, "abandoned_pending"
        return False, "pending_keep"
    return True, "unknown_status"


def purge_once(*, limit: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    from sentence_reading.llm.transfer_pack_gcs import (
        delete_pack,
        list_pack_ids,
        load_meta,
    )

    lim = purge_batch_limit() if limit is None else max(1, min(int(limit), 100))
    n = now or _utc_now()
    summary: dict[str, Any] = {
        "examined": 0,
        "purged": 0,
        "skipped": 0,
        "errors": 0,
        "dry_run": purge_dry_run(),
        "actions": [],
    }
    if not purge_enabled():
        return summary

    for pid in list_pack_ids():
        if summary["purged"] >= lim:
            break
        summary["examined"] += 1
        meta = load_meta(pid)
        if not meta:
            summary["skipped"] += 1
            continue
        ok, reason = should_purge_meta(meta, now=n)
        if not ok:
            summary["skipped"] += 1
            continue
        if purge_dry_run():
            summary["purged"] += 1
            summary["actions"].append({"pack_id": pid[:8], "reason": reason, "dry_run": True})
            continue
        result = delete_pack(pid)
        if result.get("ok"):
            summary["purged"] += 1
            summary["actions"].append({"pack_id": pid[:8], "reason": reason})
            try:
                from sentence_reading.llm import evidence_bus as eb

                eb.emit(
                    "transfer_pack_deleted",
                    ok=True,
                    code=reason,
                    details={"reason": reason},
                )
            except Exception:
                pass
        else:
            summary["errors"] += 1
    return summary
