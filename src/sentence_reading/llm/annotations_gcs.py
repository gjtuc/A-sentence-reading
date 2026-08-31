"""
무엇을: reader annotations store(v1) GCS 동기화 + latest-at 병합 (design/166).
왜: 모바일 하이라이트·메모·figure ink 계정 간 동기화.
object: {prefix}/users/{uid}/annotations/store_v1.json
충돌: annotation id별 at 최신 wins; deleted=true tombstone.
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

ANNOTATIONS_STORE_MAX_BYTES = 2_000_000


def annotations_store_object() -> str | None:
    return personal_object_name("annotations", "store_v1.json")


def empty_annotations_store() -> dict[str, Any]:
    return {"version": 1, "papers": {}}


def _as_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_annotations_store()
    papers = raw.get("papers")
    if not isinstance(papers, dict):
        return empty_annotations_store()
    ver = raw.get("version")
    if ver != 1:
        return empty_annotations_store()
    return {"version": 1, "papers": papers}


def _parse_annotation_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    aid = raw.get("id")
    at = raw.get("at")
    if not isinstance(aid, str) or not aid.strip():
        return None
    if not isinstance(at, str) or not at.strip():
        return None
    kind = str(raw.get("kind") or "highlight").strip() or "highlight"
    out: dict[str, Any] = {
        "id": aid.strip(),
        "at": at,
        "deleted": raw.get("deleted") is True,
        "kind": kind,
    }
    for key in (
        "color",
        "style",
        "motivation",
        "note",
        "sentence_id",
        "char_range",
        "selector",
        "status",
        "paths",
    ):
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
    return out


def _merge_event_arrays(left: Any, right: Any) -> list[dict[str, Any]]:
    la = left if isinstance(left, list) else []
    rb = right if isinstance(right, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for raw in [*la, *rb]:
        ev = _parse_annotation_event(raw)
        if ev is None:
            continue
        prev = by_id.get(ev["id"])
        if prev is None or (ev.get("at") or "") >= (prev.get("at") or ""):
            by_id[ev["id"]] = ev
    return list(by_id.values())


def _compact_event_array(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [ev for ev in events if isinstance(ev, dict) and not ev.get("deleted")]


def _merge_key_maps(left: Any, right: Any) -> dict[str, list[dict[str, Any]]]:
    la = left if isinstance(left, dict) else {}
    rb = right if isinstance(right, dict) else {}
    keys = set(la) | set(rb)
    out: dict[str, list[dict[str, Any]]] = {}
    for key in keys:
        if not isinstance(key, str) or not key:
            continue
        merged = _merge_event_arrays(la.get(key), rb.get(key))
        compact = _compact_event_array(merged)
        if compact:
            out[key] = compact
    return out


def merge_annotations_stores(a: Any, b: Any) -> dict[str, Any]:
    sa = _as_store(a)
    sb = _as_store(b)
    papers: dict[str, Any] = {}
    keys = set(sa["papers"]) | set(sb["papers"])
    for pk in keys:
        if not isinstance(pk, str) or not pk:
            continue
        pa = sa["papers"].get(pk) if isinstance(sa["papers"].get(pk), dict) else {}
        pb = sb["papers"].get(pk) if isinstance(sb["papers"].get(pk), dict) else {}
        sentences = _merge_key_maps(pa.get("sentences"), pb.get("sentences"))
        figures = _merge_key_maps(pa.get("figures"), pb.get("figures"))
        if sentences or figures:
            papers[pk] = {"sentences": sentences, "figures": figures}
    return {"version": 1, "papers": papers}


def encode_annotations_store(store: dict[str, Any]) -> bytes | None:
    data = merge_annotations_stores(store, empty_annotations_store())
    try:
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(raw) > ANNOTATIONS_STORE_MAX_BYTES:
        return None
    return raw


def decode_annotations_store(raw: bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    if len(raw) > ANNOTATIONS_STORE_MAX_BYTES:
        return None
    try:
        return _as_store(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def download_annotations_store() -> dict[str, Any] | None:
    obj = annotations_store_object()
    if not obj:
        return None
    return decode_annotations_store(download_bytes(obj))


def upload_annotations_store(store: dict[str, Any]) -> bool:
    obj = annotations_store_object()
    if not obj:
        return False
    raw = encode_annotations_store(store)
    if not raw:
        return False
    return upload_bytes(obj, raw, content_type="application/json; charset=utf-8")


def push_annotations_store(local: dict[str, Any]) -> dict[str, Any]:
    local_s = _as_store(local)
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return local_s
    remote = download_annotations_store() or empty_annotations_store()
    merged = merge_annotations_stores(remote, local_s)
    if not upload_annotations_store(merged):
        log.warning("annotations store upload failed — returning merge without confirm")
    return merged


def remove_paper_annotations(paper_key: str) -> bool:
    """design/102 — drop annotations for one paper key (e.g. cache:{id}). Best-effort."""
    key = (paper_key or "").strip()
    if not key:
        return False
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return False
    store = download_annotations_store() or empty_annotations_store()
    papers = store.get("papers")
    if not isinstance(papers, dict) or key not in papers:
        return True
    del papers[key]
    return upload_annotations_store({"version": 1, "papers": papers})


def annotations_gcs_status_fields() -> dict[str, Any]:
    return {
        "annotations_sync": True,
        "annotations_object": annotations_store_object(),
        "annotations_max_bytes": ANNOTATIONS_STORE_MAX_BYTES,
    }
