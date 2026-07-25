"""
무엇을: 노트 store(v2) GCS 동기화 + append-only 병합.
왜: PC 간 되새김질 텍스트(·voice 메타) 이어쓰기 (design/17).
object: {prefix}/notes/store_v2.json
충돌: 리비전 fingerprint 합집합 후 at 정렬·rev 재번호 (내용 삭제 없음).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    gcs_config,
    object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

NOTES_STORE_MAX_BYTES = 2_000_000


def notes_store_object() -> str | None:
    return object_name("notes", "store_v2.json")


def empty_notes_store() -> dict[str, Any]:
    return {"version": 2, "papers": {}}


def _as_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_notes_store()
    papers = raw.get("papers")
    if not isinstance(papers, dict):
        return empty_notes_store()
    return {"version": 2, "papers": papers}


def _text_fp(item: dict[str, Any]) -> str:
    return f"{item.get('at', '')}\n{item.get('body', '')}"


def _voice_fp(item: dict[str, Any]) -> str:
    return f"{item.get('at', '')}\n{item.get('blobKey', '')}\n{item.get('mime', '')}"


def _merge_rev_list(
    left: list[Any],
    right: list[Any],
    *,
    kind: str,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def add(seq: list[Any]) -> None:
        if not isinstance(seq, list):
            return
        for item in seq:
            if not isinstance(item, dict):
                continue
            if kind == "text":
                if not isinstance(item.get("body"), str):
                    continue
                fp = _text_fp(item)
            else:
                if not item.get("blobKey"):
                    continue
                fp = _voice_fp(item)
            if fp in seen:
                continue
            seen.add(fp)
            out.append(
                {
                    "rev": int(item["rev"]) if isinstance(item.get("rev"), int) else 0,
                    "at": str(item.get("at") or ""),
                    **(
                        {"body": item["body"]}
                        if kind == "text"
                        else {
                            "blobKey": str(item.get("blobKey") or ""),
                            "mime": str(item.get("mime") or "audio/webm"),
                        }
                    ),
                }
            )

    add(left)
    add(right)
    out.sort(key=lambda r: (r.get("at") or "", r.get("rev") or 0))
    for i, item in enumerate(out, start=1):
        item["rev"] = i
    return out


def merge_notes_stores(a: Any, b: Any) -> dict[str, Any]:
    """두 store 합집합 — append-only (동일 fingerprint는 1회)."""
    sa = _as_store(a)
    sb = _as_store(b)
    papers: dict[str, Any] = {}
    keys = set(sa["papers"]) | set(sb["papers"])
    for pk in keys:
        if not isinstance(pk, str) or not pk:
            continue
        pa = sa["papers"].get(pk) if isinstance(sa["papers"].get(pk), dict) else {}
        pb = sb["papers"].get(pk) if isinstance(sb["papers"].get(pk), dict) else {}
        sids = set(pa) | set(pb)
        paper: dict[str, Any] = {}
        for sid in sids:
            if not isinstance(sid, str) or not sid:
                continue
            ea = pa.get(sid) if isinstance(pa.get(sid), dict) else {}
            eb = pb.get(sid) if isinstance(pb.get(sid), dict) else {}
            paper[sid] = {
                "text": _merge_rev_list(ea.get("text") or [], eb.get("text") or [], kind="text"),
                "voice": _merge_rev_list(
                    ea.get("voice") or [], eb.get("voice") or [], kind="voice"
                ),
            }
        if paper:
            papers[pk] = paper
    return {"version": 2, "papers": papers}


def encode_notes_store(store: dict[str, Any]) -> bytes | None:
    data = _as_store(store)
    try:
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(raw) > NOTES_STORE_MAX_BYTES:
        return None
    return raw


def decode_notes_store(raw: bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    if len(raw) > NOTES_STORE_MAX_BYTES:
        return None
    try:
        return _as_store(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def download_notes_store() -> dict[str, Any] | None:
    obj = notes_store_object()
    if not obj:
        return None
    return decode_notes_store(download_bytes(obj))


def upload_notes_store(store: dict[str, Any]) -> bool:
    obj = notes_store_object()
    if not obj:
        return False
    raw = encode_notes_store(store)
    if not raw:
        return False
    return upload_bytes(obj, raw, content_type="application/json; charset=utf-8")


def push_notes_store(local: dict[str, Any]) -> dict[str, Any]:
    """
    remote∪local 병합 후 업로드. GCS 불가면 local만 반환.
    """
    local_s = _as_store(local)
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return local_s
    remote = download_notes_store() or empty_notes_store()
    merged = merge_notes_stores(remote, local_s)
    if not upload_notes_store(merged):
        log.warning("notes store upload failed — returning merge without confirm")
    return merged


def notes_gcs_status_fields() -> dict[str, Any]:
    return {
        "notes_sync": True,
        "notes_object": notes_store_object(),
        "notes_max_bytes": NOTES_STORE_MAX_BYTES,
    }
