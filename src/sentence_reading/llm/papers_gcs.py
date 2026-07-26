"""
무엇을: 논문 보관본(session.json + figures + source) GCS 동기화.
왜: 다른 PC에서 같은 cache_id·제목으로 열어 노트 키(cache:…)를 유지 (design/17·20).
object:
  {prefix}/papers/index.json
  {prefix}/papers/{cache_id}/session.json
  {prefix}/papers/{cache_id}/figures/{file}
  {prefix}/papers/{cache_id}/source.pdf|source.docx  (있을 때만)
"""

from __future__ import annotations

import json
import logging
import re
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
    gcs_client_ready,
    gcs_config,
    object_name,
    upload_bytes,
)
from sentence_reading.llm.typography import PIPELINE_VERSION

log = logging.getLogger(__name__)

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_FIG_FILE_RE = re.compile(r"^figures/[A-Za-z0-9._\-]+$")
_SOURCE_FILE_RE = re.compile(r"^source\.(pdf|docx)$")
PAPER_SESSION_MAX_BYTES = 5_000_000
PAPER_FIGURE_MAX_BYTES = 8_000_000
PAPER_INDEX_MAX_BYTES = 2_000_000
PAPER_SOURCE_MAX_BYTES = SOURCE_MAX_BYTES


def papers_index_object() -> str | None:
    return object_name("papers", "index.json")


def paper_session_object(cache_id: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    return object_name("papers", cid, "session.json")


def paper_figure_object(cache_id: str, rel: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    path = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not _FIG_FILE_RE.match(path):
        return None
    # figures/name.png → segments
    return object_name("papers", cid, "figures", path.split("/", 1)[1])


def paper_source_object(cache_id: str, filename: str) -> str | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    name = (filename or "").replace("\\", "/").strip().lstrip("/").split("/")[-1]
    if not _SOURCE_FILE_RE.match(name):
        return None
    return object_name("papers", cid, name)


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


def download_remote_index() -> dict[str, Any]:
    obj = papers_index_object()
    if not obj:
        return _empty_index()
    return _decode_index(download_bytes(obj))


def upload_remote_index(index: dict[str, Any]) -> bool:
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
    return upload_bytes(obj, raw, content_type="application/json; charset=utf-8")


def merge_index_entries(a: list[Any], b: list[Any]) -> list[dict[str, Any]]:
    """id 기준 최신 updated_at 우선 · 동일 title_key+source 도 최신만."""
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

    # title_key + source 충돌 → 더 새 updated_at
    by_ts: dict[tuple[str, str], dict[str, Any]] = {}
    for e in by_id.values():
        key = str(e.get("title_key") or "")
        src = str(e.get("source") or "pdf").lower()
        if not key:
            continue
        ts_key = (key, src)
        prev = by_ts.get(ts_key)
        if not prev or str(e.get("updated_at") or "") >= str(prev.get("updated_at") or ""):
            by_ts[ts_key] = e

    # id 로 다시 모으되 title 중복 제거된 집합
    kept_ids = {e["id"] for e in by_ts.values()}
    # title_key 없는 항목은 id 맵에서 유지
    for eid, e in by_id.items():
        if not str(e.get("title_key") or ""):
            kept_ids.add(eid)
    out = [by_id[i] for i in kept_ids if i in by_id]
    out.sort(key=lambda e: str(e.get("updated_at") or ""), reverse=True)
    return out


def upload_paper_cache(cache_id: str) -> bool:
    """로컬 보관본 → GCS (session + figures + index merge)."""
    ready, msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        log.debug("papers upload skip: %s", msg)
        return False
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False
    paper_dir = cache_root() / cid
    session_path = paper_dir / _SESSION_NAME
    if not session_path.is_file():
        return False
    try:
        session_raw = session_path.read_bytes()
    except OSError:
        return False
    if not session_raw or len(session_raw) > PAPER_SESSION_MAX_BYTES:
        return False
    sess_obj = paper_session_object(cid)
    if not sess_obj or not upload_bytes(
        sess_obj, session_raw, content_type="application/json; charset=utf-8"
    ):
        return False
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

    # index: local entry ∪ remote
    local_entries = list(_read_index().get("entries") or [])
    local_entry = next(
        (e for e in local_entries if isinstance(e, dict) and e.get("id") == cid),
        None,
    )
    remote = download_remote_index()
    merged = merge_index_entries(
        remote.get("entries") or [],
        [local_entry] if local_entry else local_entries,
    )
    return upload_remote_index({"version": 1, "entries": merged})


def download_paper_cache(cache_id: str, *, entry: dict[str, Any] | None = None) -> bool:
    """GCS → 로컬 보관본. 성공 시 로컬 index upsert."""
    ready, msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        log.debug("papers download skip: %s", msg)
        return False
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False
    sess_obj = paper_session_object(cid)
    if not sess_obj:
        return False
    session_raw = download_bytes(sess_obj)
    if not session_raw or len(session_raw) > PAPER_SESSION_MAX_BYTES:
        return False
    try:
        meta = json.loads(session_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(meta, dict):
        return False

    paper_dir = cache_root() / cid
    fig_dir = paper_dir / "figures"
    try:
        fig_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / _SESSION_NAME).write_bytes(session_raw)
    except OSError:
        return False

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

    # 원본 백업 pull
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


def ensure_paper_local(cache_id: str) -> bool:
    """로컬에 session 있으면 True · 없으면 GCS pull."""
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False
    if (cache_root() / cid / _SESSION_NAME).is_file():
        return True
    return download_paper_cache(cid)


def pull_paper_matching_text(text: str, *, source: str = "pdf") -> dict[str, Any] | None:
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
    remote = download_remote_index()
    best: dict[str, Any] | None = None
    best_len = 0
    for entry in remote.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        entry_src = str(entry.get("source") or "pdf").lower()
        if entry_src != want:
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
    """로컬 ∪ 원격 index 메타 (다운로드는 open/ingest 시)."""
    local = list(_read_index().get("entries") or [])
    ready, _ = gcs_client_ready()
    if gcs_config().enabled and ready:
        remote = download_remote_index().get("entries") or []
        merged = merge_index_entries(local, remote)
    else:
        merged = [e for e in local if isinstance(e, dict)]
    out = []
    for entry in merged:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("id")
        title = entry.get("title")
        if not cid or not title:
            continue
        out.append(
            {
                "id": cid,
                "title": title,
                "source": str(entry.get("source") or "pdf"),
                "updated_at": entry.get("updated_at") or "",
                "sentence_count": int(entry.get("sentence_count") or 0),
                "figure_count": int(entry.get("figure_count") or 0),
                "debone": bool(entry.get("debone")),
                "pipeline_version": str(entry.get("pipeline_version") or ""),
                "stale": str(entry.get("pipeline_version") or "") != PIPELINE_VERSION,
                "has_source": bool(entry.get("has_source"))
                or get_source_path(str(cid)) is not None,
            }
        )
    out.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    return out


def delete_paper_cache(cache_id: str) -> bool:
    """
    GCS 논문 객체·index 항목 제거.
    session/figures 삭제 + index 에서 id 제거 후 재업로드.
    """
    ready, msg = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        log.debug("papers delete skip: %s", msg)
        return False
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return False

    # session 읽어 figure 목록 확보 (없어도 index 정리는 진행)
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
        if sess_obj:
            delete_bytes(sess_obj)

    for fig in meta.get("figures") or []:
        if not isinstance(fig, dict):
            continue
        fig_obj = paper_figure_object(cid, str(fig.get("file") or ""))
        if fig_obj:
            delete_bytes(fig_obj)

    src_name = str(meta.get("source_file") or "").strip()
    if not src_name:
        src_name = source_filename_for(str(meta.get("source") or "pdf"))
    src_obj = paper_source_object(cid, src_name.split("/")[-1] if src_name else "")
    if src_obj:
        delete_bytes(src_obj)
    # 다른 확장자 잔여물
    other = "source.docx" if src_name.endswith(".pdf") else "source.pdf"
    other_obj = paper_source_object(cid, other)
    if other_obj:
        delete_bytes(other_obj)

    remote = download_remote_index()
    entries = [
        e
        for e in (remote.get("entries") or [])
        if isinstance(e, dict) and e.get("id") != cid
    ]
    return upload_remote_index({"version": 1, "entries": entries})


def papers_gcs_status_fields() -> dict[str, Any]:
    return {
        "papers_sync": True,
        "papers_index": papers_index_object(),
    }
