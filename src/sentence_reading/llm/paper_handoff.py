"""design/185 — paper handoff (manifest · file pull · ACK · cloud wipe)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_REL_SAFE_RE = re.compile(r"^[a-zA-Z0-9._\-]+(?:/[a-zA-Z0-9._\-]+)*$")
_HANDOFF_STATE_SCHEMA = 1


def handoff_enabled() -> bool:
    """Phase >= 2 advertises handoff APIs; wipe still gated by paper_local_sot."""
    from sentence_reading.llm.paper_local_sot import paper_local_sot_phase

    return paper_local_sot_phase() >= 2


def wipe_on_ack_enabled() -> bool:
    from sentence_reading.llm.paper_local_sot import paper_local_sot_enabled

    return paper_local_sot_enabled() and handoff_enabled()


def handoff_abandon_hours() -> int:
    raw = (os.environ.get("ASR_PAPER_HANDOFF_ABANDON_HOURS") or "72").strip()
    try:
        h = int(raw)
    except ValueError:
        return 72
    return max(1, min(h, 24 * 30))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash16(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _safe_rel(path: str) -> str | None:
    rel = (path or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    if not _REL_SAFE_RE.match(rel):
        return None
    # Allow only known paper artifact shapes.
    if rel == "session.json":
        return rel
    if rel in ("layout_map.json", "slot_plan.json", "manifest.json"):
        return rel
    if rel in ("source.pdf", "source.docx"):
        return rel
    if rel.startswith("figures/") and rel.endswith(".png"):
        return rel
    return None


def _handoff_state_object(cache_id: str) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    return personal_object_name("paper_handoff", f"{cid}.json")


def load_handoff_state(cache_id: str) -> dict[str, Any] | None:
    from sentence_reading.llm.gcs_sync import download_bytes, gcs_client_ready, gcs_config

    obj = _handoff_state_object(cache_id)
    if not obj:
        return None
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_handoff_acked(cache_id: str) -> bool:
    st = load_handoff_state(cache_id)
    if not st:
        return False
    return bool(st.get("acked"))


def save_handoff_state(cache_id: str, state: dict[str, Any]) -> bool:
    from sentence_reading.llm.gcs_sync import (
        gcs_client_ready,
        gcs_config,
        upload_bytes,
    )

    obj = _handoff_state_object(cache_id)
    if not obj:
        return False
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return False
    payload = dict(state)
    payload["v"] = _HANDOFF_STATE_SCHEMA
    payload["cache_id"] = (cache_id or "").strip()
    payload["updated_at"] = _utc_now().isoformat()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return bool(upload_bytes(obj, raw, content_type="application/json"))


def clear_handoff_state(cache_id: str) -> bool:
    """New ingest generation may clear prior ack so re-handoff can run."""
    from sentence_reading.llm.gcs_sync import delete_bytes, gcs_client_ready, gcs_config

    obj = _handoff_state_object(cache_id)
    if not obj:
        return False
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return False
    return bool(delete_bytes(obj))


def _list_paper_rel_paths(cache_id: str) -> list[str]:
    """Relative paths under papers/{id}/ suitable for handoff."""
    from sentence_reading.llm.gcs_sync import list_blobs_under
    from sentence_reading.llm.papers_gcs import paper_prefix_object

    cid = (cache_id or "").strip()
    prefix = paper_prefix_object(cid)
    if not prefix:
        return []
    names = list_blobs_under(prefix + "/")
    out: list[str] = []
    marker = prefix.rstrip("/") + "/"
    for name in names:
        n = str(name or "").replace("\\", "/")
        if not n.startswith(marker):
            continue
        rel = n[len(marker) :]
        safe = _safe_rel(rel)
        if safe:
            out.append(safe)
    # Prefer deterministic order: session first, then figures, then rest.
    def _key(r: str) -> tuple[int, str]:
        if r == "session.json":
            return (0, r)
        if r.startswith("figures/"):
            return (1, r)
        if r.startswith("source."):
            return (2, r)
        return (3, r)

    return sorted(set(out), key=_key)


def _read_paper_bytes(cache_id: str, rel: str) -> bytes | None:
    """Local cache first, then GCS."""
    from sentence_reading.cache.paper_cache import cache_root
    from sentence_reading.llm.gcs_sync import download_bytes
    from sentence_reading.llm.papers_gcs import paper_prefix_object

    safe = _safe_rel(rel)
    if not safe:
        return None
    cid = (cache_id or "").strip()
    local = cache_root() / cid / Path(*safe.split("/"))
    if local.is_file():
        try:
            raw = local.read_bytes()
            if raw:
                return raw
        except OSError:
            pass
    prefix = paper_prefix_object(cid)
    if not prefix:
        return None
    return download_bytes(f"{prefix}/{safe}")


def build_handoff_manifest(cache_id: str) -> dict[str, Any]:
    """Build sha256 manifest for handoff pull."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return {"ok": False, "error": "bad_cache_id"}
    if is_handoff_acked(cid):
        return {"ok": False, "error": "already_acked", "acked": True}

    files: dict[str, dict[str, Any]] = {}
    content_hash = ""
    artifact_gen = ""
    title = ""
    for rel in _list_paper_rel_paths(cid):
        raw = _read_paper_bytes(cid, rel)
        if not raw:
            continue
        files[rel] = {
            "size": len(raw),
            "sha256": _sha256_hex(raw),
        }
        if rel == "session.json":
            try:
                meta = json.loads(raw.decode("utf-8"))
                if isinstance(meta, dict):
                    content_hash = str(meta.get("content_hash") or "").strip()
                    artifact_gen = str(meta.get("artifact_gen") or "").strip()
                    title = str(meta.get("title") or "").strip()[:200]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

    if "session.json" not in files:
        return {"ok": False, "error": "no_session"}

    artifact_gen = artifact_gen or _sha256_hex(
        f"{cid}:{content_hash}:{sorted(files.keys())}".encode("utf-8")
    )[:16]

    # Persist pending handoff generation for ACK verify.
    save_handoff_state(
        cid,
        {
            "acked": False,
            "pending": True,
            "content_hash": content_hash,
            "artifact_gen": artifact_gen,
            "file_count": len(files),
            "title": title,
            "manifest_built_at": _utc_now().isoformat(),
        },
    )

    return {
        "ok": True,
        "cache_id": cid,
        "content_hash": content_hash,
        "artifact_gen": artifact_gen,
        "title": title,
        "file_count": len(files),
        "files": files,
    }


def read_handoff_file(cache_id: str, rel: str) -> tuple[bytes | None, str]:
    """Return (bytes, error_code)."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None, "bad_cache_id"
    if is_handoff_acked(cid) and wipe_on_ack_enabled():
        # After wipe, cloud files are gone — client should use local store.
        return None, "already_acked"
    safe = _safe_rel(rel)
    if not safe:
        return None, "bad_path"
    raw = _read_paper_bytes(cid, safe)
    if not raw:
        return None, "missing"
    return raw, ""


def apply_handoff_ack(
    cache_id: str,
    *,
    content_hash: str,
    artifact_gen: str,
    file_count: int,
    ok: bool = True,
) -> dict[str, Any]:
    """Verify ACK then optionally wipe cloud papers/ (not notes)."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return {"ok": False, "error": "bad_cache_id"}
    if not ok:
        return {"ok": False, "error": "client_not_ok"}
    if not handoff_enabled():
        return {"ok": False, "error": "handoff_disabled"}

    st = load_handoff_state(cid) or {}
    if st.get("acked"):
        return {
            "ok": True,
            "already_acked": True,
            "wiped": bool(st.get("wiped")),
            "cache_id": cid,
        }

    expect_gen = str(st.get("artifact_gen") or "").strip()
    expect_hash = str(st.get("content_hash") or "").strip().lower()
    expect_n = int(st.get("file_count") or 0)
    got_gen = (artifact_gen or "").strip()
    got_hash = (content_hash or "").strip().lower()
    got_n = int(file_count or 0)

    if expect_gen and got_gen and expect_gen != got_gen:
        return {"ok": False, "error": "artifact_gen_mismatch"}
    if expect_hash and got_hash and expect_hash != got_hash:
        return {"ok": False, "error": "content_hash_mismatch"}
    if expect_n and got_n and expect_n != got_n:
        return {"ok": False, "error": "file_count_mismatch"}

    wiped = False
    wipe_stats: dict[str, Any] = {}
    if wipe_on_ack_enabled():
        from sentence_reading.llm.papers_gcs import delete_paper_cache_stats

        # delete_paper_cache_stats: prefix wipe + index row — does NOT purge notes.
        wipe_stats = delete_paper_cache_stats(cid)
        wiped = bool(wipe_stats.get("ok"))
        # Also drop server-local mirror so multi-instance cannot re-upload.
        try:
            from sentence_reading.cache.paper_cache import cache_root
            import shutil

            local = cache_root() / cid
            if local.is_dir():
                shutil.rmtree(local, ignore_errors=True)
        except Exception:  # noqa: BLE001
            log.debug("local paper dir wipe skip", exc_info=True)

    save_handoff_state(
        cid,
        {
            "acked": True,
            "pending": False,
            "wiped": wiped,
            "content_hash": got_hash or expect_hash,
            "artifact_gen": got_gen or expect_gen,
            "file_count": got_n or expect_n,
            "acked_at": _utc_now().isoformat(),
            "wipe_stats": {
                "ok": wipe_stats.get("ok"),
                "residual_n": wipe_stats.get("residual_n"),
                "object_n": wipe_stats.get("object_n"),
            }
            if wipe_stats
            else {},
        },
    )

    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            "paper_handoff_done",
            ok=True,
            cache_id=cid,
            details={
                "wiped": wiped,
                "wipe_on_ack": wipe_on_ack_enabled(),
                "file_count": got_n or expect_n,
                "content_hash16": _hash16(got_hash or expect_hash),
            },
        )
        if wiped:
            eb.emit(
                "paper_cloud_wipe",
                ok=bool(wipe_stats.get("ok")),
                cache_id=cid,
                details={
                    "residual_n": wipe_stats.get("residual_n"),
                    "object_n": wipe_stats.get("object_n"),
                },
            )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "cache_id": cid,
        "wiped": wiped,
        "wipe_on_ack": wipe_on_ack_enabled(),
        "already_acked": False,
    }


def refuse_upload_if_acked(cache_id: str) -> str | None:
    """Return refuse reason if upload must not resurrect papers after ACK+wipe."""
    if not wipe_on_ack_enabled():
        return None
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    st = load_handoff_state(cid)
    if not st:
        return None
    if st.get("acked") and st.get("wiped"):
        return "handoff_acked"
    # Abandon TTL wipe — same resurrection ban until new ingest clears state.
    if st.get("abandoned") and st.get("wiped"):
        return "handoff_abandoned"
    return None



def abandon_ttl_enabled() -> bool:
    """design/185 J24 — purge stuck pending handoffs (default on)."""
    v = (os.environ.get("ASR_PAPER_HANDOFF_ABANDON_TTL") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def abandon_ttl_dry_run() -> bool:
    v = (os.environ.get("ASR_PAPER_HANDOFF_ABANDON_TTL_DRY_RUN") or "0").strip().lower()
    return v in ("1", "true", "on", "yes")


def abandon_purge_interval_sec() -> int:
    raw = (os.environ.get("ASR_PAPER_HANDOFF_ABANDON_PURGE_INTERVAL_S") or "3600").strip()
    try:
        s = int(raw)
    except ValueError:
        return 3600
    return max(300, min(s, 24 * 3600))


def abandon_purge_batch_limit() -> int:
    raw = (os.environ.get("ASR_PAPER_HANDOFF_ABANDON_PURGE_BATCH") or "20").strip()
    try:
        n = int(raw)
    except ValueError:
        return 20
    return max(1, min(n, 100))


def abandon_status_fields() -> dict[str, Any]:
    return {
        "paper_handoff_abandon_ttl": abandon_ttl_enabled(),
        "paper_handoff_abandon_hours": handoff_abandon_hours(),
        "paper_handoff_abandon_ttl_dry_run": abandon_ttl_dry_run(),
    }


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


def list_handoff_state_ids() -> list[str]:
    from sentence_reading.llm.gcs_sync import list_blobs_under, personal_object_name

    prefix = personal_object_name("paper_handoff")
    if not prefix:
        return []
    names = list_blobs_under(prefix + "/")
    out: set[str] = set()
    marker = prefix.rstrip("/") + "/"
    for name in names:
        n = str(name or "").replace("\\", "/")
        if not n.startswith(marker):
            continue
        base = n[len(marker) :]
        if not base.endswith(".json") or "/" in base:
            continue
        cid = base[:-5]
        if _CACHE_ID_RE.match(cid):
            out.add(cid)
    return sorted(out)


def should_abandon_handoff(
    state: dict[str, Any] | None, *, now: datetime | None = None
) -> tuple[bool, str]:
    """J19 — pending un-acked only; age from manifest_built_at."""
    if not isinstance(state, dict):
        return False, "no_state"
    if state.get("acked"):
        return False, "acked"
    if not state.get("pending"):
        return False, "not_pending"
    n = now or _utc_now()
    base = _parse_iso(str(state.get("manifest_built_at") or state.get("updated_at") or ""))
    if base is None:
        return False, "no_timestamp"
    if n >= base + timedelta(hours=handoff_abandon_hours()):
        return True, "abandon_ttl"
    return False, "not_yet"


def abandon_one(cache_id: str, *, reason: str = "abandon_ttl") -> dict[str, Any]:
    """Wipe papers prefix for stuck pending handoff; keep notes (J20)."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return {"ok": False, "error": "bad_cache_id"}
    from sentence_reading.llm.papers_gcs import delete_paper_cache_stats

    wipe_stats = delete_paper_cache_stats(cid)
    wiped = bool(wipe_stats.get("ok"))
    try:
        from sentence_reading.cache.paper_cache import cache_root
        import shutil

        local = cache_root() / cid
        if local.is_dir():
            shutil.rmtree(local, ignore_errors=True)
    except Exception:  # noqa: BLE001
        log.debug("local paper dir abandon wipe skip", exc_info=True)

    st = load_handoff_state(cid) or {}
    save_handoff_state(
        cid,
        {
            **st,
            "acked": False,
            "pending": False,
            "abandoned": True,
            "wiped": wiped,
            "abandon_reason": reason,
            "abandoned_at": _utc_now().isoformat(),
            "wipe_stats": {
                "ok": wipe_stats.get("ok"),
                "residual_n": wipe_stats.get("residual_n"),
                "object_n": wipe_stats.get("object_n"),
            },
        },
    )
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            "paper_handoff_abandoned",
            ok=wiped,
            cache_id=cid,
            code=reason,
            details={
                "residual_n": wipe_stats.get("residual_n"),
                "object_n": wipe_stats.get("object_n"),
            },
        )
        if wiped:
            eb.emit(
                "paper_cloud_wipe",
                ok=True,
                cache_id=cid,
                details={"reason": reason, "object_n": wipe_stats.get("object_n")},
            )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "cache_id": cid, "wiped": wiped, "stats": wipe_stats}


def purge_abandoned_once(
    *, limit: int | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Scan paper_handoff states; wipe aged pending (J19–J20)."""
    lim = abandon_purge_batch_limit() if limit is None else max(1, min(int(limit), 100))
    n = now or _utc_now()
    summary: dict[str, Any] = {
        "examined": 0,
        "purged": 0,
        "skipped": 0,
        "errors": 0,
        "dry_run": abandon_ttl_dry_run(),
        "actions": [],
    }
    if not abandon_ttl_enabled() or not handoff_enabled():
        return summary
    for cid in list_handoff_state_ids():
        if summary["purged"] >= lim:
            break
        summary["examined"] += 1
        st = load_handoff_state(cid)
        ok, reason = should_abandon_handoff(st, now=n)
        if not ok:
            summary["skipped"] += 1
            continue
        if abandon_ttl_dry_run():
            summary["purged"] += 1
            summary["actions"].append({"cache_id": cid[:8], "reason": reason, "dry_run": True})
            continue
        try:
            out = abandon_one(cid, reason=reason)
            if out.get("ok"):
                summary["purged"] += 1
                summary["actions"].append({"cache_id": cid[:8], "reason": reason})
            else:
                summary["errors"] += 1
        except Exception:  # noqa: BLE001
            summary["errors"] += 1
            log.exception("abandon purge failed %s", cid[:8])
    return summary
