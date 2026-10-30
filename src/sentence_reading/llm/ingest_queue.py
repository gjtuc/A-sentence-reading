"""
Per-user server upload queue (design/493).

users/{uid}/ingest_queue/queue.json holds job ids in upload order. A waiting job
(`queue_waiting`) has its blob in GCS but no worker; the next one starts only when
the one ahead is done, failed or cancelled, so the queue moves with the app closed.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sentence_reading.llm.gcs_sync import (
    download_bytes_generation,
    personal_object_name,
    upload_bytes_generation_match,
)

log = logging.getLogger(__name__)

QUEUE_MAX = 40
# A job flipped to start has no lease until its worker stamps one.
START_GRACE_S = 120
WAITING_MESSAGE = "차례를 기다려요"

_JOB_ID_RE = re.compile(r"^job_[a-f0-9]{12}$")
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")


def server_queue_enabled() -> bool:
    """Kill switch: ASR_INGEST_SERVER_QUEUE=0 starts every upload at once (old way)."""
    raw = (os.environ.get("ASR_INGEST_SERVER_QUEUE") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def queue_object(uid: str) -> str | None:
    from sentence_reading.llm.ingest_jobs_gcs import _with_uid

    u = (uid or "").strip()
    if not u:
        return None
    with _with_uid(u):
        return personal_object_name("ingest_queue", "queue.json")


def _clean_item(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    jid = str(row.get("job_id") or "").strip()
    if not _JOB_ID_RE.fullmatch(jid):
        return None
    h = str(row.get("content_hash") or "").strip().lower()
    return {
        "job_id": jid,
        "filename": str(row.get("filename") or "")[:180],
        "content_hash": h if _HASH_RE.fullmatch(h) else "",
        "at": str(row.get("at") or "")[:40],
    }


def parse_queue(raw: bytes | None) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    rows = data.get("items") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        item = _clean_item(row)
        if item is None or item["job_id"] in seen:
            continue
        seen.add(item["job_id"])
        out.append(item)
        if len(out) >= QUEUE_MAX:
            break
    return out


def _encode(items: list[dict[str, str]]) -> bytes:
    return json.dumps(
        {"v": 1, "items": items[:QUEUE_MAX]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def load_queue(uid: str) -> list[dict[str, str]]:
    obj = queue_object(uid)
    if not obj:
        return []
    raw, _gen = download_bytes_generation(obj, meter=False)
    return parse_queue(raw)


def mutate_queue(
    uid: str,
    fn: Callable[[list[dict[str, str]]], list[dict[str, str]]],
    *,
    tries: int = 6,
) -> list[dict[str, str]] | None:
    """Read-modify-write with a generation check. None when every try lost or failed."""
    obj = queue_object(uid)
    if not obj:
        return None
    for _ in range(max(1, tries)):
        raw, gen = download_bytes_generation(obj, meter=False)
        cur = parse_queue(raw)
        nxt = [x for x in (_clean_item(r) for r in fn(list(cur))) if x is not None]
        if nxt == cur:
            return cur
        if not nxt and gen == 0:
            return []
        res = upload_bytes_generation_match(
            obj,
            _encode(nxt),
            if_generation_match=int(gen),
            content_type="application/json",
            meter=False,
        )
        if res == "ok":
            return nxt
        if res != "conflict":
            return None
    log.warning("ingest queue write lost every race uid=%s", uid[:12])
    return None


def append_job(
    uid: str, job_id: str, *, filename: str = "", content_hash: str = ""
) -> int:
    """Add job at the end. Returns its 0-based place, or -1 when the queue was not written."""
    item = _clean_item(
        {
            "job_id": job_id,
            "filename": filename,
            "content_hash": content_hash,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if item is None:
        return -1

    def _add(cur: list[dict[str, str]]) -> list[dict[str, str]]:
        if any(x["job_id"] == item["job_id"] for x in cur):
            return cur
        if len(cur) >= QUEUE_MAX:
            return cur
        return [*cur, item]

    out = mutate_queue(uid, _add)
    if out is None:
        return -1
    for i, x in enumerate(out):
        if x["job_id"] == item["job_id"]:
            return i
    return -1


def drop_jobs(uid: str, job_ids: set[str]) -> list[dict[str, str]] | None:
    if not job_ids:
        return None
    return mutate_queue(uid, lambda cur: [x for x in cur if x["job_id"] not in job_ids])


def _parse_iso(raw: Any) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def job_finished(job: dict[str, Any] | None) -> bool:
    if not isinstance(job, dict):
        return True
    return bool(
        job.get("done")
        or job.get("error")
        or job.get("cancel_requested")
        or job.get("_discarded")
    )


def plan_advance(
    items: list[dict[str, str]],
    load: Callable[[str], dict[str, Any] | None],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Walk the queue in order. Finished or missing jobs are dropped. The first live
    job decides: waiting → start it; started and alive → busy; started but its
    lease ran out → reclaim. Jobs behind it are not loaded.
    """
    from sentence_reading.llm.ingest_jobs_gcs import lease_expired

    n = now or datetime.now(timezone.utc)
    drop: list[str] = []
    action = "idle"
    target = ""
    live_n = 0
    for it in items:
        jid = it["job_id"]
        if action != "idle":
            live_n += 1
            continue
        job = load(jid)
        if job_finished(job):
            drop.append(jid)
            continue
        live_n += 1
        target = jid
        if job.get("queue_waiting"):
            action = "start"
        elif job.get("_local_running") or not lease_expired(job, now=n):
            action = "busy"
        else:
            started = _parse_iso(job.get("queue_started_at"))
            if started is not None and n - started < timedelta(seconds=START_GRACE_S):
                action = "busy"
            else:
                action = "reclaim"
    return {"drop": drop, "action": action, "job_id": target, "live_n": live_n}


def ahead_counts(items: list[dict[str, str]], drop: list[str]) -> dict[str, int]:
    """How many live jobs sit before each job (the running one counts)."""
    gone = set(drop)
    out: dict[str, int] = {}
    n = 0
    for it in items:
        if it["job_id"] in gone:
            continue
        out[it["job_id"]] = n
        n += 1
    return out


def waiting_message(ahead: int | None) -> str:
    if ahead is None or ahead <= 0:
        return WAITING_MESSAGE
    return f"앞의 {ahead}개가 끝나면 시작해요"
