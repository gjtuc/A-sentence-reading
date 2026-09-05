"""
무엇을: 논문 보관본(session.json + figures + source) GCS 동기화.
왜: 다른 PC에서 같은 cache_id·제목으로 열어 노트 키(cache:…)를 유지 (design/17·20).
object:
  {prefix}/papers/index.json
  {prefix}/papers/{cache_id}/session.json
  {prefix}/papers/{cache_id}/figures/{file}
  {prefix}/papers/{cache_id}/layout_map.json
  {prefix}/papers/{cache_id}/slot_plan.json
  {prefix}/papers/{cache_id}/source.pdf|source.docx  (있을 때만)
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sentence_reading.cache.paper_cache import (
    SOURCE_MAX_BYTES,
    _HEAD_CHARS,
    _MIN_TITLE_KEY_LEN,
    _SESSION_NAME,
    _read_index,
    _write_index,
    cache_root,
    get_source_path,
    normalize_title_key,
    source_filename_for,
)
from sentence_reading.llm.gcs_sync import (
    delete_bytes,
    download_bytes,
    download_bytes_generation,
    gcs_client_ready,
    gcs_config,
    list_blobs_under,
    papers_index_cas_enabled,
    papers_prefix_delete_enabled,
    papers_supersede_gc_enabled,
    personal_object_name,
    upload_bytes,
    upload_bytes_generation_match,
)
from sentence_reading.llm.typography import PIPELINE_VERSION

log = logging.getLogger(__name__)

# design/159 — rate-limited lazy purge + per-uid remote index TTL cache.
_last_purge_monotonic: float | None = None
_PURGE_INTERVAL_SEC = 3600.0
_remote_index_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_REMOTE_INDEX_TTL_SEC = 45.0

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_FIG_FILE_RE = re.compile(r"^figures/[A-Za-z0-9._\-]+$")
_LAYOUT_JSON_RE = re.compile(r"^(layout_map|slot_plan)\.json$")
_SOURCE_FILE_RE = re.compile(r"^source\.(pdf|docx)$")
PAPER_SESSION_MAX_BYTES = 5_000_000
PAPER_FIGURE_MAX_BYTES = 8_000_000
PAPER_INDEX_MAX_BYTES = 2_000_000
PAPER_SOURCE_MAX_BYTES = SOURCE_MAX_BYTES


def papers_index_object() -> str | None:
    return personal_object_name("papers", "index.json")


def paper_prefix_object(cache_id: str) -> str | None:
    """design/175 — GCS directory prefix for one paper (no trailing slash)."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    return personal_object_name("papers", cid)


def paper_session_object(cache_id: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    return personal_object_name("papers", cid, "session.json")


def paper_figure_object(cache_id: str, rel: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    path = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not _FIG_FILE_RE.match(path):
        return None
    # figures/name.png → segments
    return personal_object_name("papers", cid, "figures", path.split("/", 1)[1])


def paper_layout_json_object(cache_id: str, name: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    nm = (name or "").strip()
    if not _LAYOUT_JSON_RE.match(nm):
        return None
    return personal_object_name("papers", cid, nm)


def paper_source_object(cache_id: str, filename: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    name = (filename or "").replace("\\", "/").strip().lstrip("/").split("/")[-1]
    if not _SOURCE_FILE_RE.match(name):
        return None
    return personal_object_name("papers", cid, name)


def _empty_index() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def _decode_index(raw: bytes | None) -> dict[str, Any]:
    if not raw or len(raw) > PAPER_INDEX_MAX_BYTES:
        return _empty_index()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return _empty_index()
    if not isinstance(data, dict):
        return _empty_index()
    entries = data.get("entries")
    if not isinstance(entries, list):
        data["entries"] = []
    data["version"] = 1
    return data


def invalidate_remote_index_cache() -> None:
    """design/159 — call after index upload/delete."""
    _remote_index_cache.clear()


def reset_papers_gcs_runtime_cache_for_tests() -> None:
    """Test helper — clear design/159 in-memory caches."""
    global _last_purge_monotonic
    _last_purge_monotonic = None
    _remote_index_cache.clear()


def download_remote_index() -> dict[str, Any]:
    from sentence_reading.llm.auth_google import current_gcs_uid

    uid = current_gcs_uid() or "__legacy__"
    now = time.monotonic()
    hit = _remote_index_cache.get(uid)
    if hit is not None and (now - hit[0]) < _REMOTE_INDEX_TTL_SEC:
        return hit[1]
    obj = papers_index_object()
    if not obj:
        data = _empty_index()
    else:
        data = _decode_index(download_bytes(obj))
    _remote_index_cache[uid] = (now, data)
    return data


def _maybe_purge_expired() -> list[str]:
    """Lazy TTL purge — at most once per instance hour (design/159)."""
    global _last_purge_monotonic
    from sentence_reading.cache.paper_cache import purge_expired_papers
    from sentence_reading.llm.paper_retention import retention_enabled

    if not retention_enabled():
        return []
    now = time.monotonic()
    if (
        _last_purge_monotonic is not None
        and (now - _last_purge_monotonic) < _PURGE_INTERVAL_SEC
    ):
        return []
    _last_purge_monotonic = now
    return purge_expired_papers()


def upload_remote_index(index: dict[str, Any]) -> bool:
    """Rewrite personal papers index (legacy non-CAS path). Prefer upload_remote_index_cas."""
    obj = papers_index_object()
    if not obj:
        return False
    entries = index.get("entries") if isinstance(index, dict) else None
    if not isinstance(entries, list):
        entries = []
    payload = {"version": 1, "entries": entries}
    try:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError):
        return False
    if len(raw) > PAPER_INDEX_MAX_BYTES:
        return False
    ok = upload_bytes(obj, raw, content_type="application/json; charset=utf-8")
    if ok:
        invalidate_remote_index_cache()
    return ok


def upload_remote_index_cas(
    build_entries,
    *,
    max_retries: int = 8,
) -> bool:
    """
    design/175 — download index → build_entries(remote_entries) → CAS upload.
    ``build_entries`` receives the current remote entry list and returns the next list.
    """
    obj = papers_index_object()
    if not obj:
        return False
    use_cas = papers_index_cas_enabled()
    attempts = max(1, int(max_retries))
    for _ in range(attempts):
        if use_cas:
            raw, gen = download_bytes_generation(obj)
        else:
            raw = download_bytes(obj)
            gen = 0
        remote = _decode_index(raw)
        remote_entries = list(remote.get("entries") or [])
        try:
            entries = build_entries(remote_entries)
        except Exception:  # noqa: BLE001
            return False
        if not isinstance(entries, list):
            entries = []
        payload = {"version": 1, "entries": entries}
        try:
            out = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        except (TypeError, ValueError):
            return False
        if len(out) > PAPER_INDEX_MAX_BYTES:
            return False
        if not use_cas:
            ok = upload_bytes(obj, out, content_type="application/json; charset=utf-8")
            if ok:
                invalidate_remote_index_cache()
            return bool(ok)
        status = upload_bytes_generation_match(
            obj,
            out,
            if_generation_match=int(gen),
            content_type="application/json; charset=utf-8",
        )
        if status == "ok":
            invalidate_remote_index_cache()
            return True
        if status == "conflict":
            continue
        return False
    return False


def merge_index_entries(a: list[Any], b: list[Any]) -> list[dict[str, Any]]:
    """id 기준 최신 updated_at 우선 · 동일 title_key+source+doc_role 도 최신만."""
    by_id: dict[str, dict[str, Any]] = {}
    for seq in (a, b):
        if not isinstance(seq, list):
            continue
        for e in seq:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id") or "").strip()
            if not _CACHE_ID_RE.match(eid):
                continue
            prev = by_id.get(eid)
            if not prev or str(e.get("updated_at") or "") >= str(
                prev.get("updated_at") or ""
            ):
                by_id[eid] = dict(e)
                by_id[eid]["id"] = eid

    by_ts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in by_id.values():
        key = str(e.get("title_key") or "")
        src = str(e.get("source") or "pdf").lower()
        role = str(e.get("doc_role") or "main").strip().lower()
        if not key:
            continue
        ts_key = (key, src, role)
        prev = by_ts.get(ts_key)
        if not prev or str(e.get("updated_at") or "") >= str(prev.get("updated_at") or ""):
            by_ts[ts_key] = e

    kept_ids = {e["id"] for e in by_ts.values()}
    for eid, e in by_id.items():
        if not str(e.get("title_key") or ""):
            kept_ids.add(eid)
    out = [by_id[i] for i in kept_ids if i in by_id]
    out.sort(key=lambda e: str(e.get("updated_at") or ""), reverse=True)
    return out


def merge_index_dropped_ids(
    *seqs: list[Any],
    merged: list[Any],
) -> list[str]:
    """Ids present in inputs but absent after merge (design/175 supersede losers)."""
    before: set[str] = set()
    for seq in seqs:
        if not isinstance(seq, list):
            continue
        for e in seq:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id") or "").strip()
            if _CACHE_ID_RE.match(eid):
                before.add(eid)
    after: set[str] = set()
    if isinstance(merged, list):
        for e in merged:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id") or "").strip()
            if _CACHE_ID_RE.match(eid):
                after.add(eid)
    return sorted(before - after)


def wipe_paper_prefix(cache_id: str) -> dict[str, Any]:
    """design/175 — list+delete every object under papers/{id}/."""
    cid = (cache_id or "").strip()
    empty = {
        "ok": False,
        "listed_n": 0,
        "deleted_n": 0,
        "failed_n": 0,
        "residual_n": 0,
        "skipped": 1,
    }
    if not _CACHE_ID_RE.match(cid):
        return empty
    prefix = paper_prefix_object(cid)
    if not prefix:
        return empty
    if not papers_prefix_delete_enabled():
        return {**empty, "skipped": 1, "ok": True}
    ready, _msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return empty
    # Prefer module-level list/delete so tests can monkeypatch papers_gcs bindings.
    listed = list_blobs_under(prefix + "/")
    deleted_n = 0
    failed_n = 0
    for name in listed:
        if delete_bytes(name):
            deleted_n += 1
        else:
            failed_n += 1
    residual = list_blobs_under(prefix + "/")
    residual_n = len(residual)
    return {
        "ok": residual_n == 0 and failed_n == 0,
        "listed_n": len(listed),
        "deleted_n": int(deleted_n),
        "failed_n": int(failed_n),
        "residual_n": residual_n,
        "skipped": 0,
    }


def gc_superseded_paper(cache_id: str, *, winner_id: str = "") -> dict[str, Any]:
    """design/175 — wipe loser prefix after title_key supersede; never touches index."""
    cid = (cache_id or "").strip()
    stats = {
        "ok": False,
        "cache_id": cid,
        "winner_id": str(winner_id or "").strip()[:64],
        "residual_n": 0,
        "deleted_n": 0,
        "skipped": 0,
    }
    if not papers_supersede_gc_enabled():
        stats["skipped"] = 1
        stats["ok"] = True
        return stats
    wipe = wipe_paper_prefix(cid)
    stats.update(
        {
            "ok": bool(wipe.get("ok")),
            "residual_n": int(wipe.get("residual_n") or 0),
            "deleted_n": int(wipe.get("deleted_n") or 0),
            "listed_n": int(wipe.get("listed_n") or 0),
            "failed_n": int(wipe.get("failed_n") or 0),
            "skipped": int(wipe.get("skipped") or 0),
        }
    )
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            "papers_supersede_gc",
            severity="boundary",
            cache_id=cid,
            stage="supersede_gc",
            details={
                "winner_id": stats["winner_id"],
                "deleted_n": stats["deleted_n"],
                "residual_n": stats["residual_n"],
                "skipped": stats["skipped"],
            },
            ok=bool(stats["ok"]),
            code="papers_supersede_gc",
        )
    except Exception:  # noqa: BLE001
        pass
    return stats


def _merge_session_meta_richer(remote: dict, local: dict) -> dict:
    """Prevent stale local uploads from shrinking a repaired GCS session."""
    out = dict(local)
    r_figs = remote.get("figures") or []
    l_figs = local.get("figures") or []
    if isinstance(r_figs, list) and isinstance(l_figs, list) and len(r_figs) > len(l_figs):
        out["figures"] = r_figs
    r_sents = remote.get("sentences") or []
    l_sents = local.get("sentences") or []
    if isinstance(r_sents, list) and isinstance(l_sents, list) and len(r_sents) > len(l_sents):
        ko_by_id = {
            str(s.get("id") or ""): s for s in l_sents if isinstance(s, dict)
        }
        merged_sents: list[dict] = []
        for rs in r_sents:
            if not isinstance(rs, dict):
                continue
            row = dict(rs)
            ls = ko_by_id.get(str(row.get("id") or ""))
            if ls:
                for k in ("text_ko", "text_ko_stage"):
                    lv = str(ls.get(k) or "").strip()
                    if lv and not str(row.get(k) or "").strip():
                        row[k] = lv
            merged_sents.append(row)
        out["sentences"] = merged_sents
    r_refs = remote.get("references") or []
    l_refs = local.get("references") or []
    if isinstance(r_refs, list) and isinstance(l_refs, list):
        if len(r_refs) > len(l_refs):
            out["references"] = r_refs
        elif len(l_refs) > len(r_refs):
            out["references"] = l_refs
    return out


def upload_paper_cache(cache_id: str) -> bool:
    """로컬 보관본 → GCS (session + figures + index merge)."""
    def _fail(reason: str) -> bool:
        try:
            from sentence_reading.llm import evidence_bus as eb
            from sentence_reading.llm.auth_google import current_gcs_uid

            r = str(reason or "fail").strip().lower()[:64] or "fail"
            if not re.match(r"^[a-z][a-z0-9_]{0,63}$", r):
                r = "fail"
            eb.emit(
                "papers_upload_fail",
                severity="error",
                cache_id=str(cache_id or "").strip()[:64],
                owner_uid=str(current_gcs_uid() or ""),
                stage="upload",
                details={"reason": r},
                ok=False,
                code="papers_upload_fail",
            )
        except Exception:  # noqa: BLE001
            pass
        return False

    ready, msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        log.debug("papers upload skip: %s", msg)
        return False
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return _fail("bad_cache_id")
    paper_dir = cache_root() / cid
    session_path = paper_dir / _SESSION_NAME
    if not session_path.is_file():
        return _fail("no_session_file")
    try:
        session_raw = session_path.read_bytes()
    except OSError:
        return _fail("session_read_fail")
    if not session_raw or len(session_raw) > PAPER_SESSION_MAX_BYTES:
        return _fail("session_too_large")
    sess_obj = paper_session_object(cid)
    if not sess_obj:
        # auth on + no uid → personal path None (design/174).
        return _fail("no_uid_or_object")
    remote_raw = download_bytes(sess_obj)
    if remote_raw:
        try:
            remote_meta = json.loads(remote_raw.decode("utf-8"))
            local_meta = json.loads(session_raw.decode("utf-8"))
            if isinstance(remote_meta, dict) and isinstance(local_meta, dict):
                merged = _merge_session_meta_richer(remote_meta, local_meta)
                r_figs = remote_meta.get("figures") or []
                l_figs = local_meta.get("figures") or []
                r_sents = remote_meta.get("sentences") or []
                l_sents = local_meta.get("sentences") or []
                r_refs = remote_meta.get("references") or []
                l_refs = local_meta.get("references") or []
                m_figs = merged.get("figures") or []
                m_sents = merged.get("sentences") or []
                m_refs = merged.get("references") or []
                changed = (
                    len(m_figs) != len(l_figs)
                    or len(m_sents) != len(l_sents)
                    or len(m_refs) != len(l_refs)
                )
                if changed:
                    try:
                        from sentence_reading.llm import ops_events as oev

                        oev.emit(
                            "merge_session_richer",
                            cache_id=cid,
                            details={
                                "remote_figures": len(r_figs)
                                if isinstance(r_figs, list)
                                else 0,
                                "local_figures": len(l_figs)
                                if isinstance(l_figs, list)
                                else 0,
                                "merged_figures": len(m_figs)
                                if isinstance(m_figs, list)
                                else 0,
                                "remote_sentences": len(r_sents)
                                if isinstance(r_sents, list)
                                else 0,
                                "local_sentences": len(l_sents)
                                if isinstance(l_sents, list)
                                else 0,
                                "merged_sentences": len(m_sents)
                                if isinstance(m_sents, list)
                                else 0,
                            },
                        )
                    except Exception:  # noqa: BLE001
                        pass
                session_raw = (
                    json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                try:
                    session_path.write_bytes(session_raw)
                except OSError:
                    pass
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    if not upload_bytes(
        sess_obj, session_raw, content_type="application/json; charset=utf-8"
    ):
        return _fail("session_upload_fail")
    # design/169i I1 — local → gcs session transfer
    try:
        import time as _time

        from sentence_reading.llm import artifact_ids as aid

        t0 = _time.perf_counter()
        h16 = aid.hash16(session_raw)
        gen = 0
        try:
            meta_tmp = json.loads(session_raw.decode("utf-8"))
            if isinstance(meta_tmp, dict):
                gen = int(meta_tmp.get("artifact_gen") or 0)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            gen = 0
        aid.emit_artifact_transfer(
            activity="gcs_upload_session",
            from_locator=aid.locator_local_session(cid),
            to_locator=aid.locator_gcs_session(cid),
            artifact_kind="session_json",
            content_hash=h16,
            bytes_n=len(session_raw),
            gen=gen or None,
            agent="cloud_run",
            elapsed_ms=int((_time.perf_counter() - t0) * 1000),
            ok=True,
            cache_id=cid,
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        meta = json.loads(session_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        meta = {}
    for fig in meta.get("figures") or []:
        if not isinstance(fig, dict):
            continue
        rel = str(fig.get("file") or "")
        fig_obj = paper_figure_object(cid, rel)
        if not fig_obj:
            continue
        fpath = paper_dir / rel.replace("\\", "/")
        if not fpath.is_file():
            continue
        try:
            raw = fpath.read_bytes()
        except OSError:
            continue
        if not raw or len(raw) > PAPER_FIGURE_MAX_BYTES:
            continue
        upload_bytes(fig_obj, raw, content_type="application/octet-stream")

    for layout_name in ("layout_map.json", "slot_plan.json"):
        local = paper_dir / layout_name
        if not local.is_file():
            continue
        try:
            raw = local.read_bytes()
        except OSError:
            continue
        if not raw or len(raw) > PAPER_SESSION_MAX_BYTES:
            continue
        obj = paper_layout_json_object(cid, layout_name)
        if obj:
            upload_bytes(obj, raw, content_type="application/json; charset=utf-8")

    # 원본 PDF/DOCX (있을 때만)
    src_name = str(meta.get("source_file") or "") or source_filename_for(
        str(meta.get("source") or "pdf")
    )
    src_path = paper_dir / src_name if src_name else None
    if src_path is None or not src_path.is_file():
        local_src = get_source_path(cid)
        src_path = local_src
        src_name = local_src.name if local_src else ""
    if src_path is not None and src_path.is_file() and src_name:
        src_obj = paper_source_object(cid, src_name)
        if src_obj:
            try:
                raw = src_path.read_bytes()
            except OSError:
                raw = b""
            if raw and len(raw) <= PAPER_SOURCE_MAX_BYTES:
                ctype = (
                    "application/pdf"
                    if src_name.endswith(".pdf")
                    else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                upload_bytes(src_obj, raw, content_type=ctype)

    # index: local entry ∪ remote (CAS) · supersede losers get prefix GC (design/175)
    local_entries = list(_read_index().get("entries") or [])
    local_entry = next(
        (e for e in local_entries if isinstance(e, dict) and e.get("id") == cid),
        None,
    )
    local_side: list[Any] = [local_entry] if local_entry else list(local_entries)
    losers_final: list[str] = []

    def _build(remote_entries: list[Any]) -> list[dict[str, Any]]:
        nonlocal losers_final
        merged = merge_index_entries(remote_entries, local_side)
        losers_final = [
            x
            for x in merge_index_dropped_ids(remote_entries, local_side, merged=merged)
            if x != cid
        ]
        return merged

    if not upload_remote_index_cas(_build):
        # Objects may already be written — mark fail; caller/174 must not claim listed.
        return _fail("index_upload_fail")

    if losers_final and papers_supersede_gc_enabled():
        for loser in losers_final:
            gc_superseded_paper(loser, winner_id=cid)
    return True


def ensure_paper_in_remote_index(cache_id: str, *, retries: int = 1) -> bool:
    """Push paper to personal GCS index and confirm the id is listed (design/174).

    When GCS is off / not ready → True (local-only). Auth on without uid → False.
    """
    from sentence_reading.llm.auth_google import auth_enabled, current_gcs_uid

    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False
    ready, _msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return True
    if auth_enabled() and not current_gcs_uid():
        # Same hole as upload with no personal path.
        try:
            from sentence_reading.llm import evidence_bus as eb

            eb.emit(
                "papers_upload_fail",
                severity="error",
                cache_id=cid,
                stage="ensure",
                details={"reason": "no_uid"},
                ok=False,
                code="papers_upload_fail",
            )
        except Exception:  # noqa: BLE001
            pass
        return False
    attempts = max(1, int(retries) + 1)
    for _ in range(attempts):
        invalidate_remote_index_cache()
        if not upload_paper_cache(cid):
            continue
        invalidate_remote_index_cache()
        remote = download_remote_index()
        ids = {
            e.get("id")
            for e in (remote.get("entries") or [])
            if isinstance(e, dict) and e.get("id")
        }
        if cid in ids:
            return True
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            "papers_upload_fail",
            severity="error",
            cache_id=cid,
            owner_uid=str(current_gcs_uid() or ""),
            stage="ensure",
            details={"reason": "index_miss_after_upload"},
            ok=False,
            code="papers_upload_fail",
        )
    except Exception:  # noqa: BLE001
        pass
    return False


def download_paper_cache(
    cache_id: str,
    *,
    entry: dict[str, Any] | None = None,
    include_figures: bool = True,
    include_source: bool = True,
) -> bool:
    """GCS → 로컬 보관본. 성공 시 로컬 index upsert.

    design/129 — ``include_figures=False`` skips PNG pull so /open stays fast;
    single figures are fetched later via ``ensure_figure_local``.
    """
    def _fail(reason: str) -> bool:
        try:
            from sentence_reading.llm import evidence_bus as eb

            r = str(reason or "fail").strip().lower()[:64] or "fail"
            if not re.match(r"^[a-z][a-z0-9_]{0,63}$", r):
                r = "fail"
            eb.emit(
                "download_cache_fail",
                severity="error",
                cache_id=str(cache_id or "").strip()[:64],
                stage="download",
                details={
                    "include_figures": 1 if include_figures else 0,
                    "include_source": 1 if include_source else 0,
                    "reason": r,
                },
                ok=False,
                code="download_cache_fail",
            )
        except Exception:  # noqa: BLE001
            pass
        return False

    ready, msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        log.debug("papers download skip: %s", msg)
        return _fail("gcs_not_ready")
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return _fail("bad_cache_id")
    sess_obj = paper_session_object(cid)
    if not sess_obj:
        return _fail("no_session_object")
    session_raw = download_bytes(sess_obj)
    if not session_raw or len(session_raw) > PAPER_SESSION_MAX_BYTES:
        return _fail("session_missing")
    try:
        meta = json.loads(session_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail("session_bad_json")
    if not isinstance(meta, dict):
        return _fail("session_not_dict")

    paper_dir = cache_root() / cid
    fig_dir = paper_dir / "figures"
    try:
        fig_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / _SESSION_NAME).write_bytes(session_raw)
    except OSError:
        return _fail("local_write_fail")
    # design/169i I1 — gcs → local session transfer
    try:
        from sentence_reading.llm import artifact_ids as aid

        h16 = aid.hash16(session_raw)
        gen = 0
        if isinstance(meta, dict):
            try:
                gen = int(meta.get("artifact_gen") or 0)
            except (TypeError, ValueError):
                gen = 0
        aid.emit_artifact_transfer(
            activity="gcs_download_session",
            from_locator=aid.locator_gcs_session(cid),
            to_locator=aid.locator_local_session(cid),
            artifact_kind="session_json",
            content_hash=h16,
            bytes_n=len(session_raw),
            gen=gen or None,
            agent="cloud_run",
            ok=True,
            cache_id=cid,
        )
    except Exception:  # noqa: BLE001
        pass

    if include_figures:
        for fig in meta.get("figures") or []:
            if not isinstance(fig, dict):
                continue
            rel = str(fig.get("file") or "")
            fig_obj = paper_figure_object(cid, rel)
            if not fig_obj:
                continue
            raw = download_bytes(fig_obj)
            if not raw or len(raw) > PAPER_FIGURE_MAX_BYTES:
                continue
            out = paper_dir / rel.replace("\\", "/")
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(raw)
            except OSError:
                continue

    for layout_name in ("layout_map.json", "slot_plan.json"):
        obj = paper_layout_json_object(cid, layout_name)
        if not obj:
            continue
        raw = download_bytes(obj)
        if not raw or len(raw) > PAPER_SESSION_MAX_BYTES:
            continue
        try:
            (paper_dir / layout_name).write_bytes(raw)
        except OSError:
            continue

    # 원본 백업 pull
    if include_source:
        src_rel = str(meta.get("source_file") or "").strip()
        if not src_rel and meta.get("has_source"):
            src_rel = source_filename_for(str(meta.get("source") or "pdf"))
        if src_rel and ".." not in src_rel.split("/"):
            src_obj = paper_source_object(cid, src_rel.split("/")[-1])
            if src_obj:
                raw = download_bytes(src_obj)
                if raw and len(raw) <= PAPER_SOURCE_MAX_BYTES:
                    out = paper_dir / src_rel.split("/")[-1]
                    try:
                        out.write_bytes(raw)
                        meta["has_source"] = True
                        meta["source_file"] = out.name
                        try:
                            (paper_dir / _SESSION_NAME).write_text(
                                json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                            )
                        except OSError:
                            pass
                    except OSError:
                        pass

    # local index upsert
    index = _read_index()
    entries = [e for e in (index.get("entries") or []) if isinstance(e, dict)]
    new_entry = dict(entry) if isinstance(entry, dict) else {}
    has_src = bool(meta.get("has_source")) or get_source_path(cid) is not None
    new_entry.update(
        {
            "id": cid,
            "title": str(meta.get("title") or new_entry.get("title") or "Untitled"),
            "title_key": str(
                meta.get("title_key")
                or normalize_title_key(str(meta.get("title") or ""))
            ),
            "source": str(meta.get("source") or new_entry.get("source") or "pdf"),
            "updated_at": str(
                meta.get("saved_at")
                or meta.get("updated_at")
                or new_entry.get("updated_at")
                or ""
            ),
            "created_at": str(
                meta.get("created_at") or new_entry.get("created_at") or ""
            ),
            "sentence_count": len(meta.get("sentences") or []),
            "figure_count": len(meta.get("figures") or []),
            "debone": bool(meta.get("debone")),
            "pipeline_version": str(meta.get("pipeline_version") or ""),
            "has_source": has_src,
            "content_hash": str(meta.get("content_hash") or "") or None,
        }
    )
    entries = [e for e in entries if e.get("id") != cid]
    entries.insert(0, new_entry)
    index["entries"] = entries
    _write_index(index)
    return True


def local_session_has_sentences(cache_id: str) -> bool:
    """True when local session.json exists and has ≥1 non-empty sentence text."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False
    meta_path = cache_root() / cid / _SESSION_NAME
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(meta, dict):
        return False
    for s in meta.get("sentences") or []:
        if isinstance(s, dict) and str(s.get("text") or "").strip():
            return True
    return False


def ensure_paper_local(cache_id: str) -> bool:
    """Ensure a usable local session (design/114).

    WHY: a zero-byte / title-only local session.json made open succeed with
    empty reader (title from library index). Re-pull from GCS when unusable.

    NOTE: library **open** uses ``refresh_paper_for_open`` (design/121) instead —
    that path always pulls when GCS is ready and never falls back on pull fail.
    """
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False
    if local_session_has_sentences(cid):
        return True
    # EDGE: missing or empty local → always try GCS (overwrite).
    return download_paper_cache(cid)


def paper_open_require_sentences() -> bool:
    """Kill: ASR_PAPER_OPEN_REQUIRE_SENTENCES=0 allows empty open (debug only)."""
    import os

    raw = (os.environ.get("ASR_PAPER_OPEN_REQUIRE_SENTENCES") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def paper_open_gcs_first() -> bool:
    """Kill: ASR_PAPER_OPEN_GCS_FIRST=0 restores design/114 skip-when-local-ok."""
    import os

    raw = (os.environ.get("ASR_PAPER_OPEN_GCS_FIRST") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def gcs_papers_ready() -> bool:
    """True when papers may be pulled from the signed-in user's GCS prefix."""
    ready, _ = gcs_client_ready()
    return bool(gcs_config().enabled and ready)


def refresh_paper_for_open(cache_id: str) -> tuple[bool, str]:
    """Prepare local cache for library open (design/121).

    Returns ``(ok, code)``:
    - ``("ok")`` — GCS ready and download succeeded (local overwritten)
    - ``("gcs_skipped")`` — GCS off/not ready; caller may open local (dev)
    - ``("gcs_pull_failed")`` — GCS ready but pull failed → **do not** open local
    - ``("bad_cache_id")`` — invalid id

    WHY: shared instance disk can hold another user's leftover session.json.
    Always overwriting from ``personal_object_name`` prevents opening that
    leftover when the signed-in user's GCS object is missing/unreadable.
    """
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False, "bad_cache_id"
    if not paper_open_gcs_first():
        # Kill off → 114: only pull when local unusable.
        return (True, "ok") if ensure_paper_local(cid) else (False, "gcs_pull_failed")
    if not gcs_papers_ready():
        # EDGE: local-only / GCS not ready — not a pull failure (product 4).
        return True, "gcs_skipped"
    # Product 1A: always pull session (design/121). design/129: skip bulk PNGs/source.
    if not download_paper_cache(cid, include_figures=False, include_source=False):
        # Product 2A: refuse local fallback (fail-closed).
        return False, "gcs_pull_failed"
    return True, "ok"


def ensure_figure_local_with_reason(
    cache_id: str, figure_rel: str
) -> tuple[Path | None, str]:
    """design/129+168d — local Path or (None, reason enum)."""
    cid = (cache_id or "").strip()
    rel = (figure_rel or "").replace("\\", "/").strip()
    if not _CACHE_ID_RE.match(cid):
        return None, "bad_cache_id"
    if not _FIG_FILE_RE.match(rel):
        return None, "bad_rel"
    paper_dir = cache_root() / cid
    out = paper_dir / rel
    if out.is_file() and out.stat().st_size > 0:
        return out, "local_ok"
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled:
        return (out if out.is_file() else None), "gcs_disabled"
    if not ready:
        return (out if out.is_file() else None), "gcs_not_ready"
    fig_obj = paper_figure_object(cid, rel)
    if not fig_obj:
        return None, "object_denied"
    raw = download_bytes(fig_obj)
    if not raw:
        return None, "download_empty"
    if len(raw) > PAPER_FIGURE_MAX_BYTES:
        return None, "download_too_large"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
    except OSError:
        return None, "write_failed"
    if out.is_file():
        return out, "ok"
    return None, "write_failed"


def ensure_figure_local(cache_id: str, figure_rel: str) -> Path | None:
    """design/129 — download one figure object to disk if missing.

    SECURITY: only ``figures/…`` under this cache_id via paper_figure_object.
    design/168d — emits ``figure_blob_miss`` on miss (reason in details).
    """
    path, reason = ensure_figure_local_with_reason(cache_id, figure_rel)
    if path is not None:
        return path
    try:
        from sentence_reading.llm import ops_events as oev

        oev.emit(
            "figure_blob_miss",
            cache_id=(cache_id or "").strip(),
            details={"reason": reason},
        )
    except Exception:  # noqa: BLE001
        pass
    return None


def pull_paper_matching_text(
    text: str, *, source: str = "pdf", doc_role: str = "main"
) -> dict[str, Any] | None:
    """
    원격 index 에서 제목 매칭 → 다운로드 → entry 반환.
    find_cached_by_text 로컬 miss 후 호출.
    """
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return None
    if not (text or "").strip():
        return None
    head = normalize_title_key(text[:_HEAD_CHARS])
    if len(head) < _MIN_TITLE_KEY_LEN:
        return None
    want = (source or "pdf").lower()
    want_role = (doc_role or "main").strip().lower()
    remote = download_remote_index()
    best: dict[str, Any] | None = None
    best_len = 0
    for entry in remote.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        entry_src = str(entry.get("source") or "pdf").lower()
        if entry_src != want:
            continue
        entry_role = str(entry.get("doc_role") or "main").strip().lower()
        if entry_role != want_role:
            continue
        key = str(entry.get("title_key") or "")
        if len(key) < _MIN_TITLE_KEY_LEN:
            continue
        if key in head and len(key) > best_len:
            best = entry
            best_len = len(key)
    if not best or not best.get("id"):
        return None
    cid = str(best["id"])
    if not download_paper_cache(cid, entry=best):
        return None
    return best


def list_merged_paper_entries() -> list[dict[str, Any]]:
    """로컬 ∪ 원격 index 메타 (다운로드는 open/ingest 시).

    Multi-tenant (0.2.87 · design/70):
    - auth on + no UID → empty (do not leak instance-local disk to strangers)
    - personal GCS index present → only merge local rows already in that remote index
    """
    from sentence_reading.cache.paper_cache import _retention_list_fields
    from sentence_reading.cache.supplementary_library import list_entries_for_api
    from sentence_reading.llm.auth_google import auth_enabled, current_gcs_uid

    t_total = time.perf_counter()

    t0 = time.perf_counter()
    purged = _maybe_purge_expired()
    t_purge = time.perf_counter() - t0

    uid = current_gcs_uid()
    if auth_enabled() and not uid:
        log.info(
            "cache_papers_timing purge=%.3fs purged_n=%d local_read=0.000 "
            "gcs_index=0.000 merge=0.000 enrich=0.000 total=%.3fs papers=0 uid=",
            t_purge,
            len(purged),
            time.perf_counter() - t_total,
        )
        return []

    t1 = time.perf_counter()
    local = list(_read_index().get("entries") or [])
    t_local = time.perf_counter() - t1

    t2 = time.perf_counter()
    ready, _ = gcs_client_ready()
    remote_entries: list[Any] = []
    if gcs_config().enabled and ready and papers_index_object():
        remote_entries = download_remote_index().get("entries") or []
    t_gcs_index = time.perf_counter() - t2

    t3 = time.perf_counter()
    if gcs_config().enabled and ready and papers_index_object():
        remote_ids = {
            e.get("id") for e in remote_entries if isinstance(e, dict) and e.get("id")
        }
        local_mine = [
            e for e in local if isinstance(e, dict) and e.get("id") in remote_ids
        ]
        merged = merge_index_entries(local_mine, remote_entries)
    elif gcs_config().enabled and ready:
        merged = []
    else:
        merged = [e for e in local if isinstance(e, dict)]
    t_merge = time.perf_counter() - t3

    t4 = time.perf_counter()
    rows = list_entries_for_api(merged)
    by_id = {str(e.get("id") or ""): e for e in merged if isinstance(e, dict)}
    out = []
    for row in rows:
        cid = str(row.get("id") or "")
        src_entry = by_id.get(cid) or {}
        out.append(
            {
                **row,
                "pipeline_version": str(row.get("pipeline_version") or src_entry.get("pipeline_version") or ""),
                "stale": str(src_entry.get("pipeline_version") or "") != PIPELINE_VERSION,
                "has_source": bool(row.get("has_source"))
                or get_source_path(cid) is not None,
                **_retention_list_fields(src_entry),
            }
        )
    out.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    t_enrich = time.perf_counter() - t4

    log.info(
        "cache_papers_timing purge=%.3fs purged_n=%d local_read=%.3fs "
        "gcs_index=%.3fs merge=%.3fs enrich=%.3fs total=%.3fs papers=%d uid=%s",
        t_purge,
        len(purged),
        t_local,
        t_gcs_index,
        t_merge,
        t_enrich,
        time.perf_counter() - t_total,
        len(out),
        uid or "",
    )
    return out


def delete_paper_cache(cache_id: str) -> bool:
    """
    GCS 논문 객체·index 항목 제거.
    session/figures 삭제 + index 에서 id 제거 후 재업로드.
    """
    stats = delete_paper_cache_stats(cache_id)
    return bool(stats.get("ok"))


def delete_paper_cache_stats(cache_id: str) -> dict[str, Any]:
    """
    design/169g phase 4 + design/175 — prefix wipe then CAS index remove.
    Returns ``{ok, object_n, figure_n, residual_n, skipped}`` (no paper text).
    ``ok`` only when residual_n==0 and index rewrite succeeded.
    """
    ready, msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        log.debug("papers delete skip: %s", msg)
        return {
            "ok": False,
            "object_n": 0,
            "figure_n": 0,
            "residual_n": 0,
            "skipped": 1,
        }
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return {
            "ok": False,
            "object_n": 0,
            "figure_n": 0,
            "residual_n": 0,
            "skipped": 1,
        }

    object_n = 0
    figure_n = 0

    # Legacy meta walk (fast path for known paths) then mandatory prefix wipe.
    sess_obj = paper_session_object(cid)
    session_raw = download_bytes(sess_obj) if sess_obj else None
    meta: dict[str, Any] = {}
    if session_raw:
        try:
            parsed = json.loads(session_raw.decode("utf-8"))
            if isinstance(parsed, dict):
                meta = parsed
        except (UnicodeDecodeError, json.JSONDecodeError):
            meta = {}
        if sess_obj and delete_bytes(sess_obj):
            object_n += 1

    for fig in meta.get("figures") or []:
        if not isinstance(fig, dict):
            continue
        fig_obj = paper_figure_object(cid, str(fig.get("file") or ""))
        if fig_obj and delete_bytes(fig_obj):
            object_n += 1
            figure_n += 1

    src_name = str(meta.get("source_file") or "").strip()
    if not src_name:
        src_name = source_filename_for(str(meta.get("source") or "pdf"))
    src_obj = paper_source_object(cid, src_name.split("/")[-1] if src_name else "")
    if src_obj and delete_bytes(src_obj):
        object_n += 1
    other = "source.docx" if src_name.endswith(".pdf") else "source.pdf"
    other_obj = paper_source_object(cid, other)
    if other_obj and delete_bytes(other_obj):
        object_n += 1
    for layout_name in ("layout_map.json", "slot_plan.json"):
        layout_obj = paper_layout_json_object(cid, layout_name)
        if layout_obj and delete_bytes(layout_obj):
            object_n += 1

    wipe = wipe_paper_prefix(cid)
    object_n += int(wipe.get("deleted_n") or 0)
    residual_n = int(wipe.get("residual_n") or 0)

    def _build(remote_entries: list[Any]) -> list[dict[str, Any]]:
        return [
            e
            for e in (remote_entries or [])
            if isinstance(e, dict) and e.get("id") != cid
        ]

    index_ok = bool(upload_remote_index_cas(_build))
    if index_ok:
        object_n += 1

    # Re-check residual after index update (dense).
    if papers_prefix_delete_enabled():
        prefix = paper_prefix_object(cid)
        if prefix:
            residual_n = len(list_blobs_under(prefix + "/"))

    ok = bool(index_ok) and residual_n == 0
    if residual_n > 0:
        try:
            from sentence_reading.llm import evidence_bus as eb

            eb.emit(
                "papers_delete_residual",
                severity="error",
                cache_id=cid,
                stage="delete",
                details={
                    "residual_n": residual_n,
                    "deleted_n": int(wipe.get("deleted_n") or 0),
                    "index_ok": bool(index_ok),
                },
                ok=False,
                code="papers_delete_residual",
            )
        except Exception:  # noqa: BLE001
            pass

    try:
        from sentence_reading.llm import artifact_ids as aid

        aid.emit_artifact_invalidate(
            locator=aid.locator_gcs_session(cid),
            artifact_kind="session_json",
            activity="paper_delete_gcs",
            ok=ok,
            cache_id=cid,
            object_n=object_n,
            figure_n=figure_n,
        )
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": ok,
        "object_n": int(object_n),
        "figure_n": int(figure_n),
        "residual_n": int(residual_n),
        "skipped": 0,
    }


def papers_gcs_status_fields() -> dict[str, Any]:
    return {
        "papers_sync": True,
        "papers_index": papers_index_object(),
        "papers_prefix_delete": papers_prefix_delete_enabled(),
        "papers_supersede_gc": papers_supersede_gc_enabled(),
        "papers_index_cas": papers_index_cas_enabled(),
    }
