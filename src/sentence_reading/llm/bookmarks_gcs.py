"""
무엇을: 북마크 store(v1) GCS 동기화 + latest-at 병합.
왜: 모바일 리더 문장/Figure 북마크 계정 간 동기화.
object: {prefix}/users/{uid}/bookmarks/store_v1.json
충돌: 키별 at 최신 이벤트 승리; deleted=true면 북마크 아님.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    gcs_config,
    personal_object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

BOOKMARKS_STORE_MAX_BYTES = 500_000


def bookmarks_store_object() -> str | None:
    return personal_object_name("bookmarks", "store_v1.json")


def empty_bookmarks_store() -> dict[str, Any]:
    return {"version": 1, "papers": {}}


def _as_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_bookmarks_store()
    papers = raw.get("papers")
    if not isinstance(papers, dict):
        return empty_bookmarks_store()
    ver = raw.get("version")
    if ver != 1:
        return empty_bookmarks_store()
    return {"version": 1, "papers": papers}


def _parse_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    at = raw.get("at")
    if not isinstance(at, str) or not at.strip():
        return None
    deleted = raw.get("deleted") is True
    return {"at": at, "deleted": deleted}


def _merge_event_maps(left: Any, right: Any) -> dict[str, Any]:
    la = left if isinstance(left, dict) else {}
    rb = right if isinstance(right, dict) else {}
    keys = set(la) | set(rb)
    out: dict[str, Any] = {}
    for key in keys:
        if not isinstance(key, str) or not key:
            continue
        ea = _parse_event(la.get(key))
        eb = _parse_event(rb.get(key))
        if ea is None and eb is None:
            continue
        if ea is None:
            out[key] = eb
        elif eb is None:
            out[key] = ea
        elif (eb.get("at") or "") >= (ea.get("at") or ""):
            out[key] = eb
        else:
            out[key] = ea
    return out


def _compact_events(events: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in events.items()
        if isinstance(v, dict) and not v.get("deleted")
    }


def merge_bookmarks_stores(a: Any, b: Any) -> dict[str, Any]:
    sa = _as_store(a)
    sb = _as_store(b)
    papers: dict[str, Any] = {}
    keys = set(sa["papers"]) | set(sb["papers"])
    for pk in keys:
        if not isinstance(pk, str) or not pk:
            continue
        pa = sa["papers"].get(pk) if isinstance(sa["papers"].get(pk), dict) else {}
        pb = sb["papers"].get(pk) if isinstance(sb["papers"].get(pk), dict) else {}
        sentences = _compact_events(
            _merge_event_maps(pa.get("sentences"), pb.get("sentences"))
        )
        figures = _compact_events(
            _merge_event_maps(pa.get("figures"), pb.get("figures"))
        )
        if sentences or figures:
            papers[pk] = {"sentences": sentences, "figures": figures}
    return {"version": 1, "papers": papers}


def encode_bookmarks_store(store: dict[str, Any]) -> bytes | None:
    data = merge_bookmarks_stores(store, empty_bookmarks_store())
    try:
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(raw) > BOOKMARKS_STORE_MAX_BYTES:
        return None
    return raw


def decode_bookmarks_store(raw: bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    if len(raw) > BOOKMARKS_STORE_MAX_BYTES:
        return None
    try:
        return _as_store(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def download_bookmarks_store() -> dict[str, Any] | None:
    obj = bookmarks_store_object()
    if not obj:
        return None
    return decode_bookmarks_store(download_bytes(obj))


def upload_bookmarks_store(store: dict[str, Any]) -> bool:
    obj = bookmarks_store_object()
    if not obj:
        return False
    raw = encode_bookmarks_store(store)
    if not raw:
        return False
    return upload_bytes(obj, raw, content_type="application/json; charset=utf-8")


def push_bookmarks_store(local: dict[str, Any]) -> dict[str, Any]:
    local_s = _as_store(local)
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return local_s
    remote = download_bookmarks_store() or empty_bookmarks_store()
    merged = merge_bookmarks_stores(remote, local_s)
    if not upload_bookmarks_store(merged):
        log.warning("bookmarks store upload failed — returning merge without confirm")
    return merged


def remove_paper_bookmarks(paper_key: str) -> bool:
    """design/102 — drop bookmarks for one paper key (e.g. cache:{id}). Best-effort."""
    key = (paper_key or "").strip()
    if not key:
        return False
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return False
    store = download_bookmarks_store() or empty_bookmarks_store()
    papers = store.get("papers")
    if not isinstance(papers, dict) or key not in papers:
        return True
    del papers[key]
    return upload_bookmarks_store({"version": 1, "papers": papers})


def bookmarks_gcs_status_fields() -> dict[str, Any]:
    return {
        "bookmarks_sync": True,
        "bookmarks_object": bookmarks_store_object(),
        "bookmarks_max_bytes": BOOKMARKS_STORE_MAX_BYTES,
    }
