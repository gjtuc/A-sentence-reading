"""
무엇을: 논문 제목 키로 정제 세션을 디스크에 보관·조회.
왜: 같은 논문을 다시 열 때 Gemini/추출을 반복하지 않는다. 파일명이 아니라 제목으로 대조.
어디에: <repo>/data/cache/papers/{id}/session.json + figures/*.png
"""

from __future__ import annotations

import base64
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import Figure, PaperSession, Sentence

_INDEX_NAME = "index.json"
_SESSION_NAME = "session.json"
_MIN_TITLE_KEY_LEN = 24
_HEAD_CHARS = 14_000
# WHY: 제목 대조는 키 문자열 포함 여부만 — 1000개도 수십 ms 이하. 디스크·목록 상한.
_MAX_CACHED_PAPERS = 1000
# 원본 PDF/DOCX 백업 상한 (초과 시 session만 보관)
SOURCE_MAX_BYTES = 80_000_000
_SOURCE_NAMES = {"pdf": "source.pdf", "docx": "source.docx"}


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def cache_root() -> Path:
    return project_root() / "data" / "cache" / "papers"


def normalize_title_key(title: str) -> str:
    """제목 대조용 키 — 대소문자·구두점·공백 차이 무시."""
    t = unicodedata.normalize("NFKC", title or "")
    t = re.sub(r"^\s*(title)\s*:\s*", "", t, flags=re.IGNORECASE)
    t = t.casefold()
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _index_path() -> Path:
    return cache_root() / _INDEX_NAME


def _read_index() -> dict:
    path = _index_path()
    if not path.is_file():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": []}
    if not isinstance(data, dict):
        return {"version": 1, "entries": []}
    entries = data.get("entries")
    if not isinstance(entries, list):
        data["entries"] = []
    return data


def _write_index(data: dict) -> None:
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    path = _index_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _decode_data_url(src: str) -> tuple[bytes, str] | None:
    """data:image/...;base64,... → (bytes, ext)."""
    if not src or not src.startswith("data:"):
        return None
    try:
        header, b64 = src.split(",", 1)
    except ValueError:
        return None
    mime = "image/png"
    if ";" in header:
        mime = header[5:].split(";", 1)[0] or mime
    ext = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
        "image/svg+xml": "svg",
    }.get(mime, "bin")
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return None
    if not raw:
        return None
    return raw, ext


def _figure_file_rel_n(fig_meta: list) -> int:
    n = 0
    for row in fig_meta:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("file") or "").strip().replace("\\", "/")
        if rel.startswith("figures/") and ".." not in rel.split("/"):
            n += 1
    return n


def _emit_figure_meta_boundary(
    *,
    cache_id: str,
    art_gen: int,
    activity: str,
    session_fig_n: int,
    fig_meta: list,
    prior_png_n: int,
    decoded_src_n: int,
    preserved_n: int,
    prior_meta_for_gen: dict,
    forced: bool,
    content_hash: str = "",
) -> None:
    """design/169l L1 — save boundary figure meta observability. Never raises."""
    try:
        from sentence_reading.llm import evidence_bus as eb

        cid = str(cache_id or "").strip()
        fig_meta_n = len(fig_meta)
        file_rel_n = _figure_file_rel_n(fig_meta)
        missing_file_n = max(0, session_fig_n - file_rel_n)
        sample_missing_ids: list[str] = []
        for row in fig_meta:
            if not isinstance(row, dict):
                continue
            fid = str(row.get("id") or "").strip()
            rel = str(row.get("file") or "").strip()
            if fid and not rel.startswith("figures/"):
                sample_missing_ids.append(fid)
            if len(sample_missing_ids) >= 8:
                break
        meta_ok = file_rel_n == session_fig_n if session_fig_n > 0 else True
        write_details = {
            "gen": int(art_gen),
            "activity": activity,
            "session_fig_n": session_fig_n,
            "fig_meta_n": fig_meta_n,
            "file_rel_n": file_rel_n,
            "prior_png_n": prior_png_n,
            "decoded_src_n": decoded_src_n,
            "preserved_n": preserved_n,
            "missing_file_n": missing_file_n,
        }
        if sample_missing_ids:
            write_details["sample_missing_ids"] = sample_missing_ids
        eb.emit(
            "figure_meta_write",
            severity="boundary",
            cache_id=cid,
            content_hash=content_hash,
            stage="save",
            details=write_details,
            ok=meta_ok,
            code="figure_meta_ok" if meta_ok else "figure_meta_incomplete",
        )
        prev_figs = (
            prior_meta_for_gen.get("figures")
            if isinstance(prior_meta_for_gen, dict)
            else []
        )
        prev_file_rel_n = _figure_file_rel_n(prev_figs if isinstance(prev_figs, list) else [])
        gen_prev = 0
        if isinstance(prior_meta_for_gen, dict):
            try:
                gen_prev = int(prior_meta_for_gen.get("artifact_gen") or 0)
            except (TypeError, ValueError):
                gen_prev = 0
        if prev_file_rel_n > file_rel_n and prev_file_rel_n > 0:
            eb.emit(
                "figure_meta_regress",
                severity="consistency",
                cache_id=cid,
                content_hash=content_hash,
                stage="save",
                details={
                    "gen_prev": gen_prev,
                    "gen_new": int(art_gen),
                    "prev_file_rel_n": prev_file_rel_n,
                    "new_file_rel_n": file_rel_n,
                },
                ok=False,
                code="file_rel_regress",
            )
        preserve_miss = bool(forced and prior_png_n == 0 and session_fig_n > 0)
        if (
            session_fig_n > 0
            and preserved_n == 0
            and prior_png_n > 0
            and not preserve_miss
        ):
            eb.emit(
                "figure_preserve_skip",
                severity="consistency",
                cache_id=cid,
                content_hash=content_hash,
                stage="save",
                details={
                    "reason": "prior_bytes_unused",
                    "prior_png_n": prior_png_n,
                    "session_fig_n": session_fig_n,
                    "forced": 1 if forced else 0,
                    "activity": activity,
                },
                ok=False,
                code="figure_preserve_skip",
            )
    except Exception:  # noqa: BLE001
        pass


def _figure_to_data_url(path: Path) -> str:
    raw = path.read_bytes()
    ext = path.suffix.lower().lstrip(".") or "png"
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


_FIG_ID_SAFE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def figure_data_url_with_reason(
    cache_id: str, figure_id: str
) -> tuple[str | None, str]:
    """design/129+168d — data-URL or (None, reason enum). Never invent bytes."""
    cid = (cache_id or "").strip()
    fid = (figure_id or "").strip()
    # SECURITY: reject path segments / absolute paths / odd ids.
    if not re.fullmatch(r"[a-zA-Z0-9]{8,32}", cid):
        return None, "bad_cache_id"
    if not _FIG_ID_SAFE.fullmatch(fid):
        return None, "bad_figure_id"
    root = cache_root() / cid
    meta_path = root / _SESSION_NAME
    if not meta_path.is_file():
        return None, "session_meta_missing"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "session_meta_corrupt"
    for f in meta.get("figures") or []:
        if not isinstance(f, dict):
            continue
        if str(f.get("id") or "") != fid:
            continue
        rel = str(f.get("file") or "").replace("\\", "/")
        # SECURITY: only figures/… under this paper root.
        if not rel.startswith("figures/") or ".." in rel.split("/"):
            return None, "bad_file_rel"
        img_path = (root / rel).resolve()
        try:
            img_path.relative_to(root.resolve())
        except ValueError:
            return None, "path_escape"
        if not img_path.is_file():
            # design/129 — open may skip bulk PNG pull; fetch this one from GCS.
            try:
                from sentence_reading.llm.papers_gcs import ensure_figure_local_with_reason
                from sentence_reading.llm import ops_events as oev

                ensured, ensure_reason = ensure_figure_local_with_reason(cid, rel)
                if ensured is not None:
                    img_path = ensured.resolve()
                elif ensure_reason not in ("local_ok", "ok"):
                    # design/168d G1.5 — blob miss even when called via data-URL path.
                    try:
                        oev.emit(
                            "figure_blob_miss",
                            cache_id=cid,
                            details={"reason": ensure_reason},
                        )
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:
                return None, "ensure_exception"
        if not img_path.is_file():
            return None, "file_missing"
        try:
            return _figure_to_data_url(img_path), "ok"
        except OSError:
            return None, "read_oserror"
    return None, "figure_id_not_in_meta"


def figure_data_url(cache_id: str, figure_id: str) -> str | None:
    """design/129 — load one figure PNG from disk as data-URL (no path traversal).

    Returns None when id/cache is bad or the file is missing (honest miss).
    design/168d — emits ``figure_data_url_miss`` on miss (reason in details).
    """
    url, reason = figure_data_url_with_reason(cache_id, figure_id)
    if url:
        return url
    try:
        from sentence_reading.llm import ops_events as oev
        from sentence_reading.llm import evidence_bus as eb

        miss_details = {"reason": reason, "figure_id": (figure_id or "").strip()}
        oev.emit(
            "figure_data_url_miss",
            cache_id=(cache_id or "").strip(),
            details=miss_details,
        )
        eb.emit(
            "figure_data_url_miss",
            severity="consistency",
            cache_id=(cache_id or "").strip(),
            stage="figure_data_url",
            details=miss_details,
            ok=False,
            code=str(reason or "miss")[:64],
        )
    except Exception:  # noqa: BLE001
        pass
    return None


def find_cached_by_text(
    text: str, *, source: str = "pdf", doc_role: str = "main"
) -> dict | None:
    """
    원문 앞부분에 캐시된 논문 제목이 들어 있으면 그 entry 반환.
    source(pdf/docx) + doc_role(main/supplementary) 가 같은 항목만.
    가장 긴 title_key 일치를 고른다.
    """
    if not (text or "").strip():
        return None
    head = normalize_title_key(text[:_HEAD_CHARS])
    if len(head) < _MIN_TITLE_KEY_LEN:
        return None
    want = (source or "pdf").lower()
    want_role = (doc_role or "main").strip().lower()
    if want_role not in ("main", "supplementary", "merged"):
        want_role = "main"

    best: dict | None = None
    best_len = 0
    for entry in _read_index().get("entries", []):
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
    if best is not None:
        return best
    # WHY: 로컬 miss → GCS index 제목 매칭 후 session+figures pull (design/17)
    try:
        from sentence_reading.llm.papers_gcs import pull_paper_matching_text

        return pull_paper_matching_text(text, source=source, doc_role=doc_role)
    except Exception:
        return None


def _delete_paper_dir(cache_id: str) -> None:
    import shutil

    path = cache_root() / cache_id
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def get_index_entry(cache_id: str) -> dict | None:
    """Return raw index row for cache_id (local index)."""
    cid = (cache_id or "").strip()
    if not cid:
        return None
    for entry in _read_index().get("entries") or []:
        if isinstance(entry, dict) and entry.get("id") == cid:
            return dict(entry)
    return None


def patch_index_entry(
    cache_id: str,
    updates: dict | None = None,
    **fields: object,
) -> dict | None:
    """Merge updates into one index row · sync GCS best-effort."""
    cid = (cache_id or "").strip()
    patch: dict = dict(updates or {})
    patch.update(fields)
    if not cid or not patch:
        return None
    index = _read_index()
    entries: list = list(index.get("entries") or [])
    target: dict | None = None
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("id") == cid:
            row = dict(entry)
            for key, val in patch.items():
                if val is None:
                    row.pop(key, None)
                else:
                    row[key] = val
            entries[i] = row
            target = row
            break
    if target is None:
        return None
    index["entries"] = entries
    _write_index(index)
    try:
        from sentence_reading.llm.papers_gcs import upload_paper_cache

        upload_paper_cache(cid)
    except Exception:
        pass
    return target


def sync_index_counts_from_session(cache_id: str) -> dict | None:
    """design/168f — set index sentence/figure_count from session.json (Ni/Cu repair).

    Does not invent figures; only aligns counts with persisted meta.
    """
    cid = (cache_id or "").strip()
    if not cid:
        return None
    loaded = load_cached_session(cid, load_images=False)
    if loaded is None:
        return None
    session, _info = loaded
    return patch_index_entry(
        cid,
        figure_count=len(session.figures),
        sentence_count=len(session.sentences),
    )


def purge_expired_papers() -> list[str]:
    """Lazy TTL purge — returns deleted cache_ids (design/144)."""
    from sentence_reading.llm.paper_retention import (
        ensure_entry_retention,
        is_expired,
        retention_enabled,
    )

    if not retention_enabled():
        return []
    deleted: list[str] = []
    to_purge: list[str] = []
    for entry in _read_index().get("entries") or []:
        if not isinstance(entry, dict):
            continue
        cid = str(entry.get("id") or "").strip()
        if not cid:
            continue
        row = ensure_entry_retention(entry)
        if row.get("expires_at") != entry.get("expires_at"):
            patch_index_entry(cid, {"expires_at": row.get("expires_at")})
        if is_expired(row):
            to_purge.append(cid)
    for cid in to_purge:
        if delete_cached_paper(cache_id=cid) is not None:
            deleted.append(cid)
    return deleted

def delete_cached_paper(
    *,
    cache_id: str | None = None,
    title: str | None = None,
    source: str | None = None,
) -> dict | None:
    """
    보관본 삭제. cache_id 우선, 없으면 title+source 로 찾음.
    로컬 폴더·index 제거 후 GCS index/객체도 best-effort 삭제.
    반환: 삭제된 entry(또는 stub) · 아무 것도 없으면 None.
    """
    index = _read_index()
    entries: list = list(index.get("entries") or [])
    target = None
    cid = (cache_id or "").strip()
    if cid:
        for e in entries:
            if isinstance(e, dict) and e.get("id") == cid:
                target = e
                break
    if target is None and title:
        key = normalize_title_key(title)
        src = (source or "pdf").lower()
        if src not in ("pdf", "docx"):
            src = "pdf"
        for e in entries:
            if not isinstance(e, dict):
                continue
            entry_src = str(e.get("source") or "pdf").lower()
            if e.get("title_key") == key and entry_src == src:
                target = e
                break
            if normalize_title_key(str(e.get("title") or "")) == key and entry_src == src:
                target = e
                break

    tid = str((target or {}).get("id") or cid or "").strip()
    if not tid:
        return None

    paper_path = cache_root() / tid
    had_local_dir = paper_path.is_dir()
    had_local_entry = target is not None

    _delete_paper_dir(tid)
    index["entries"] = [
        e for e in entries if not (isinstance(e, dict) and e.get("id") == tid)
    ]
    _write_index(index)

    remote_ok = False
    gcs_object_n = 0
    gcs_figure_n = 0
    gcs_skipped = 0
    try:
        from sentence_reading.llm.papers_gcs import delete_paper_cache_stats

        stats = delete_paper_cache_stats(tid)
        remote_ok = bool(stats.get("ok"))
        gcs_object_n = int(stats.get("object_n") or 0)
        gcs_figure_n = int(stats.get("figure_n") or 0)
        gcs_skipped = int(stats.get("skipped") or 0)
    except Exception:
        remote_ok = False

    # design/102 — purge same-uid notes / shadowing records (best-effort).
    try:
        from sentence_reading.llm.auth_google import current_gcs_uid
        from sentence_reading.llm import notes_gcs as ng
        from sentence_reading.llm import bookmarks_gcs as bg
        from sentence_reading.llm import annotations_gcs as an
        from sentence_reading.llm import shadowing_chunks as sc
        from sentence_reading.llm import shadowing_takes as st

        uid = current_gcs_uid() or ""
        ng.remove_paper_notes(f"cache:{tid}")
        bg.remove_paper_bookmarks(f"cache:{tid}")
        an.remove_paper_annotations(f"cache:{tid}")
        if uid:
            sc.delete_chunk_plan(uid=uid, cache_id=tid)
            st.delete_takes(uid=uid, cache_id=tid)
    except Exception:
        pass

    def _with_gcs_meta(row: dict) -> dict:
        # design/169g — counts only; stripped before any public JSON if needed.
        out = dict(row)
        out["_gcs_ok"] = 1 if remote_ok else 0
        out["_gcs_object_n"] = gcs_object_n
        out["_gcs_figure_n"] = gcs_figure_n
        out["_gcs_skipped"] = gcs_skipped
        out["_had_local"] = 1 if had_local_dir else 0
        return out

    if had_local_entry and isinstance(target, dict):
        return _with_gcs_meta(target)
    if had_local_dir or remote_ok:
        return _with_gcs_meta(
            {
                "id": tid,
                "title": str((target or {}).get("title") or title or ""),
                "source": str((target or {}).get("source") or source or "pdf"),
            }
        )
    return None



def _evict_oldest(entries: list, *, keep: int = _MAX_CACHED_PAPERS) -> list:
    """생성 시각(created_at)이 가장 오래된 것부터 제거. 디스크 폴더도 삭제."""
    valid = [e for e in entries if isinstance(e, dict) and e.get("id")]
    if len(valid) <= keep:
        return valid

    def created_key(e: dict) -> str:
        return str(e.get("created_at") or e.get("updated_at") or "")

    # 오래된 순으로 정렬 후 초과분 삭제
    ordered = sorted(valid, key=created_key)
    drop = ordered[: max(0, len(ordered) - keep)]
    drop_ids = {str(e["id"]) for e in drop}
    for e in drop:
        _delete_paper_dir(str(e["id"]))
    return [e for e in valid if str(e.get("id")) not in drop_ids]


def _retention_list_fields(entry: dict) -> dict:
    from sentence_reading.llm.paper_retention import (
        ensure_entry_retention,
        retention_enabled,
        retention_public,
    )

    if not retention_enabled():
        return {"retention": retention_public(entry)}
    row = ensure_entry_retention(entry)
    cid = str(entry.get("id") or "").strip()
    if cid and row.get("expires_at") != entry.get("expires_at"):
        patch_index_entry(cid, {"expires_at": row.get("expires_at")})
    out = {"expires_at": row.get("expires_at"), "retention": retention_public(row)}
    return out


def list_cached_papers() -> list[dict]:
    from sentence_reading.cache.supplementary_library import list_entries_for_api

    entries = [e for e in _read_index().get("entries", []) if isinstance(e, dict)]
    rows = list_entries_for_api(entries)
    for row in rows:
        cid = row.get("id")
        if not cid:
            continue
        for entry in entries:
            if entry.get("id") == cid:
                row.update(_retention_list_fields(entry))
                row["stale"] = str(entry.get("pipeline_version") or "") != PIPELINE_VERSION
                break
    rows.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    return rows


def _load_references(raw: object) -> list:
    from sentence_reading.cite_refs import bibliography_public

    return bibliography_public(raw if isinstance(raw, list) else None)


def _load_document_citation(raw: object) -> dict:
    from sentence_reading.document_citation import public_document_citation

    return public_document_citation(raw if isinstance(raw, dict) else {})


def load_cached_session(
    cache_id: str, *, load_images: bool = True
) -> tuple[PaperSession, dict] | None:
    """Load session JSON (+ optional PNG inlining).

    design/129 — ``load_images=False`` skips reading figure files so /open is fast;
    clients pull bytes via ``figure_data_url``.
    """
    root = cache_root() / cache_id
    meta_path = root / _SESSION_NAME
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    sentences = [
        Sentence(
            id=str(s.get("id") or f"s-{i}"),
            text=str(s.get("text") or ""),
            section=s.get("section"),
            text_ko=str(s.get("text_ko") or ""),
            text_ko_stage=str(s.get("text_ko_stage") or ""),
            quality_flags=tuple(
                str(f).strip()
                for f in (s.get("quality_flags") or [])
                if str(f).strip()
            ),
        )
        for i, s in enumerate(meta.get("sentences") or [])
        if isinstance(s, dict) and str(s.get("text") or "").strip()
    ]

    figures: list[Figure] = []
    for i, f in enumerate(meta.get("figures") or []):
        if not isinstance(f, dict):
            continue
        rel = f.get("file")
        fig_id = str(f.get("id") or f"fig-{i + 1:04d}")
        caption = str(f.get("caption") or "")
        caption_ko = str(f.get("caption_ko") or "")
        caption_ko_stage = str(f.get("caption_ko_stage") or "")
        page_index = f.get("page_index")
        src = ""
        # design/124 — keep caption slot when PNG missing (honest empty, not silent drop).
        if load_images and rel:
            img_path = root / str(rel)
            if img_path.is_file():
                try:
                    src = _figure_to_data_url(img_path)
                except OSError:
                    # EDGE: unreadable file → empty image_src, still list the row.
                    src = ""
            # else: file path recorded but bytes gone (GCS partial / disk loss)
        elif load_images and f.get("image_src"):
            # Legacy session rows that still embed data URLs.
            src = str(f.get("image_src") or "")
        figures.append(
            Figure(
                id=fig_id,
                image_src=src,
                caption=caption,
                page_index=page_index,
                caption_ko=caption_ko,
                caption_ko_stage=caption_ko_stage,
                slot_key=str(f.get("slot_key") or ""),
            )
        )

    title = str(meta.get("title") or "Untitled")
    digests_raw = meta.get("translate_digests") or {}
    digests: dict = {}
    if isinstance(digests_raw, dict):
        for k, v in digests_raw.items():
            if isinstance(v, dict):
                digests[str(k)] = {
                    "en": str(v.get("en") or ""),
                    "ko": str(v.get("ko") or ""),
                }
    session = PaperSession(
        title=title,
        figures=figures,
        sentences=sentences,
        figure_index=int(meta.get("figure_index") or 0),
        sentence_index=int(meta.get("sentence_index") or 0),
        translate_digests=digests,
        references=_load_references(meta.get("references")),
        document_citation=_load_document_citation(meta.get("document_citation")),
    )
    session.clamp_indices()
    info = {
        "cache_id": cache_id,
        "debone": bool(meta.get("debone")),
        "from_cache": True,
        "pipeline_version": str(meta.get("pipeline_version") or ""),
        "stale": str(meta.get("pipeline_version") or "") != PIPELINE_VERSION,
        "has_source": bool(meta.get("has_source"))
        or get_source_path(cache_id) is not None,
        "content_hash": str(meta.get("content_hash") or "") or None,
        "doc_role": str(meta.get("doc_role") or "main"),
        "supplementary_merged": bool(meta.get("supplementary_merged")),
        "supplementary_cache_id": str(meta.get("supplementary_cache_id") or "") or None,
        "warnings": list(meta.get("warnings") or []),
        "ingest_quality": meta.get("ingest_quality")
        if isinstance(meta.get("ingest_quality"), dict)
        else {},
    }
    return session, info


def source_filename_for(kind: str) -> str:
    src = (kind or "pdf").lower()
    if src not in _SOURCE_NAMES:
        src = "pdf"
    return _SOURCE_NAMES[src]


def get_source_path(cache_id: str) -> Path | None:
    """로컬 원본 경로. 없으면 None."""
    cid = (cache_id or "").strip()
    if not cid:
        return None
    paper_dir = cache_root() / cid
    for name in _SOURCE_NAMES.values():
        p = paper_dir / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    # session.json 힌트
    meta_path = paper_dir / _SESSION_NAME
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rel = str((meta or {}).get("source_file") or "")
            if rel and ".." not in rel.split("/"):
                p = paper_dir / rel
                if p.is_file() and p.stat().st_size > 0:
                    return p
        except (OSError, json.JSONDecodeError):
            pass
    return None


def backfill_references_from_source_pdf(cache_id: str) -> bool:
    """Re-extract References from source PDF when ingest text was truncated.

    WHY: debone body text often misses the full bibliography block; the stored
    PDF still has all numbered entries (acsanm QA: 21 → 43 refs).
    """
    cid = (cache_id or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9]{8,32}", cid):
        return False
    meta_path = cache_root() / cid / _SESSION_NAME
    if not meta_path.is_file():
        return False
    src = get_source_path(cid)
    if src is None or src.suffix.lower() != ".pdf":
        return False
    try:
        import fitz

        doc = fitz.open(src)
        try:
            full_text = "".join(page.get_text() for page in doc)
        finally:
            doc.close()
    except Exception:
        return False
    if not full_text.strip():
        return False
    from sentence_reading.cite_refs import bibliography_public, extract_bibliography

    new_refs = bibliography_public(extract_bibliography(full_text))
    if not new_refs:
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(meta, dict):
        return False
    old_refs = meta.get("references") or []
    old_n = len(old_refs) if isinstance(old_refs, list) else 0
    if len(new_refs) <= old_n:
        return False
    meta["references"] = new_refs
    try:
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def attach_source_file(
    cache_id: str,
    source_path: Path,
    *,
    source: str = "pdf",
) -> bool:
    """
    기존 보관본에 원본이 없을 때만 복사 (캐시 히트 시 백필).
    index/session has_source 갱신.
    """
    import shutil

    cid = (cache_id or "").strip()
    if not cid or not source_path or not source_path.is_file():
        return False
    if get_source_path(cid) is not None:
        return True
    try:
        size = source_path.stat().st_size
    except OSError:
        return False
    if size <= 0 or size > SOURCE_MAX_BYTES:
        return False
    src = (source or "pdf").lower()
    if src not in _SOURCE_NAMES:
        src = "pdf"
    paper_dir = cache_root() / cid
    if not (paper_dir / _SESSION_NAME).is_file():
        return False
    dest_name = source_filename_for(src)
    dest = paper_dir / dest_name
    try:
        paper_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
    except OSError:
        return False

    # session + index 메타
    try:
        meta = json.loads((paper_dir / _SESSION_NAME).read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            meta["has_source"] = True
            meta["source_file"] = dest_name
            (paper_dir / _SESSION_NAME).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError):
        pass
    index = _read_index()
    for e in index.get("entries") or []:
        if isinstance(e, dict) and e.get("id") == cid:
            e["has_source"] = True
            break
    _write_index(index)
    try:
        from sentence_reading.llm.papers_gcs import upload_paper_cache

        upload_paper_cache(cid)
    except Exception:
        pass
    return True


def save_layout_artifacts(
    paper_dir: Path,
    *,
    layout_map: dict | None = None,
    slot_plan: dict | None = None,
    prior_slot_plan=None,
) -> None:
    """Persist design/151 layout_map.json + slot_plan.json beside session."""
    from sentence_reading.pdf.layout_map import LayoutMap, save_layout_map
    from sentence_reading.pdf.slot_plan import SlotPlan, merge_user_confirmed_slots, save_slot_plan

    paper_dir.mkdir(parents=True, exist_ok=True)
    if layout_map:
        save_layout_map(paper_dir, LayoutMap.from_dict(layout_map))
    if slot_plan:
        plan = SlotPlan.from_dict(slot_plan)
        plan = merge_user_confirmed_slots(plan, prior_slot_plan)
        save_slot_plan(paper_dir, plan)


def save_paper_session(
    session: PaperSession,
    *,
    debone: bool = False,
    warnings: list[str] | None = None,
    ingest_quality: dict | None = None,
    source: str = "pdf",
    doc_role: str = "main",
    source_path: Path | None = None,
    content_hash: str | None = None,
    layout_artifacts: dict | None = None,
    supplementary_merged: bool = False,
    supplementary_cache_id: str | None = None,
    merge_revision: int | None = None,
    ingest_status: str = "ok",
    force_cache_id: str | None = None,
) -> dict | None:
    """
    제목 키 + source(pdf/docx) + doc_role 로 저장.
    같은 제목이어도 본편 PDF 와 보충 PDF 는 서로 덮어쓰지 않음.
    source_path 가 있으면 source.pdf|docx 로 원본 백업 (한도 초과 시 생략).
    content_hash 는 원본 바이트 SHA-256 (진행 복원 교차 키).
    ingest_status: design/168c — processing|partial|error|ok (기본 ok).
    """
    import shutil

    from sentence_reading.pdf.supplementary_detect import normalize_doc_role

    title = (session.title or "").strip()
    key = normalize_title_key(title)
    if len(key) < _MIN_TITLE_KEY_LEN:
        return None
    if not session.sentences:
        return None
    from sentence_reading.llm.ingest_jobs_gcs import normalize_ingest_status

    status = normalize_ingest_status(ingest_status)
    src = (source or "pdf").lower()
    if src not in ("pdf", "docx"):
        src = "pdf"
    role = normalize_doc_role(doc_role)
    if supplementary_merged:
        role = "merged"
    ch = (content_hash or "").strip().lower()
    if ch and not re.fullmatch(r"[a-f0-9]{64}", ch):
        ch = ""

    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)

    index = _read_index()
    entries: list = index.setdefault("entries", [])
    existing_id = None
    forced = (force_cache_id or "").strip()
    if forced and re.fullmatch(r"[a-zA-Z0-9]{8,32}", forced):
        existing_id = forced
    else:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_src = str(entry.get("source") or "pdf").lower()
            entry_role = str(entry.get("doc_role") or "main").strip().lower()
            if entry.get("title_key") == key and entry_src == src and entry_role == role:
                existing_id = entry.get("id")
                break

    now = datetime.now(timezone.utc).isoformat()
    created_at = now
    if existing_id:
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") == existing_id:
                created_at = str(entry.get("created_at") or entry.get("updated_at") or now)
                break

    cache_id = str(existing_id or uuid.uuid4().hex[:12])
    paper_dir = root / cache_id
    fig_dir = paper_dir / "figures"
    prior_slot_plan = None
    prior_meta_for_gen: dict = {}
    # design/168f T9 — snapshot prior PNG bytes before rmtree so stub rows
    # (empty image_src) can keep captions + files instead of vanishing from meta.
    prior_fig_bytes: dict[str, bytes] = {}
    prior_fig_ext: dict[str, str] = {}
    prior_fig_meta: dict[str, str] = {}
    if existing_id:
        # WHY: reanalyze on Cloud Run often has session.json but no local PNGs
        # (open is lazy). Pull figures once so T9 preserve can work.
        old_fig_dir = root / str(existing_id) / "figures"
        need_pull = not old_fig_dir.is_dir() or not any(old_fig_dir.glob("*"))
        if need_pull:
            try:
                from sentence_reading.llm.papers_gcs import (
                    download_paper_cache,
                    gcs_papers_ready,
                )

                if gcs_papers_ready():
                    download_paper_cache(
                        str(existing_id),
                        include_figures=True,
                        include_source=False,
                    )
            except Exception:  # noqa: BLE001
                pass
        from sentence_reading.pdf.slot_plan import load_slot_plan

        prior_slot_plan = load_slot_plan(root / str(existing_id))
        old_dir = root / str(existing_id)
        old_meta_path = old_dir / _SESSION_NAME
        if old_meta_path.is_file():
            try:
                old_meta = json.loads(old_meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                old_meta = {}
            if isinstance(old_meta, dict):
                prior_meta_for_gen = old_meta
            for f in old_meta.get("figures") or []:
                if not isinstance(f, dict):
                    continue
                fid = str(f.get("id") or "").strip()
                rel = str(f.get("file") or "").replace("\\", "/")
                if not fid or not rel.startswith("figures/") or ".." in rel.split("/"):
                    continue
                prior_fig_meta[fid] = rel
                img_path = old_dir / rel
                if not img_path.is_file():
                    continue
                try:
                    raw = img_path.read_bytes()
                except OSError:
                    continue
                if not raw:
                    continue
                prior_fig_bytes[fid] = raw
                ext = img_path.suffix.lower().lstrip(".") or "png"
                prior_fig_ext[fid] = ext
    # design/169 — reanalyze overwrite with zero prior PNGs is a consistency hole.
    # design/169k K1 / 169i I3 — missing_locators (filename only) on preserve miss.
    if forced and not prior_fig_bytes and len(session.figures or []) > 0:
        try:
            from sentence_reading.llm import evidence_bus as eb
            from sentence_reading.llm.artifact_ids import locator_local_figure

            cid = str(existing_id or cache_id or "")
            missing_locators: list[str] = []
            for i, fig in enumerate(session.figures):
                fid = str(fig.id or f"fig-{i + 1:04d}").strip() or f"fig-{i + 1:04d}"
                fname = re.sub(r"[^\w.\-]+", "_", f"{fid}.png")
                loc = locator_local_figure(cid, fname)
                if loc:
                    missing_locators.append(loc.rsplit("/", 1)[-1])
            eb.emit(
                "figure_preserve_miss",
                severity="consistency",
                cache_id=cid,
                details={
                    "prior_png": 0,
                    "session_figs": len(session.figures or []),
                    "forced": 1,
                    "missing_locators": missing_locators[:48],
                },
                ok=False,
                code="figure_preserve_miss",
            )
        except Exception:  # noqa: BLE001
            pass
    if paper_dir.exists():
        # 옛 그림·원본 정리 후 재기록
        shutil.rmtree(paper_dir, ignore_errors=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig_meta: list[dict] = []
    decoded_src_n = 0
    preserved_from_prior_n = 0
    for i, fig in enumerate(session.figures):
        fid = str(fig.id or f"fig-{i + 1:04d}").strip() or f"fig-{i + 1:04d}"
        decoded = _decode_data_url(fig.image_src)
        file_rel = ""
        if decoded:
            raw, ext = decoded
            fname = f"{fid}.{ext}"
            fname = re.sub(r"[^\w.\-]+", "_", fname)
            (fig_dir / fname).write_bytes(raw)
            file_rel = f"figures/{fname}"
            decoded_src_n += 1
        elif fid in prior_fig_bytes:
            # WHY: lazy open / translate re-save often has empty image_src but PNG on disk.
            ext = prior_fig_ext.get(fid) or "png"
            fname = f"{fid}.{ext}"
            fname = re.sub(r"[^\w.\-]+", "_", fname)
            (fig_dir / fname).write_bytes(prior_fig_bytes[fid])
            file_rel = f"figures/{fname}"
            preserved_from_prior_n += 1
        elif fid in prior_fig_meta:
            # design/169l — meta file rel survived but bytes not local (Cloud Run lazy open).
            rel = prior_fig_meta[fid]
            fname = re.sub(r"[^\w.\-]+", "_", rel.split("/")[-1])
            dest = fig_dir / fname
            try:
                from sentence_reading.llm.papers_gcs import ensure_figure_local_with_reason

                ensured, _ensure_reason = ensure_figure_local_with_reason(
                    str(existing_id or cache_id), rel
                )
                if ensured is not None and ensured.is_file():
                    raw = ensured.read_bytes()
                    if raw:
                        dest.write_bytes(raw)
                        file_rel = f"figures/{fname}"
                        preserved_from_prior_n += 1
            except Exception:  # noqa: BLE001
                pass
        # design/168f — always keep a meta row (stub OK). Never shrink fig_meta vs session.
        row: dict = {
            "id": fid,
            "caption": fig.caption,
            "caption_ko": fig.caption_ko or "",
            "caption_ko_stage": fig.caption_ko_stage or "",
            "page_index": fig.page_index,
            "slot_key": fig.slot_key or "",
        }
        if file_rel:
            row["file"] = file_rel
        fig_meta.append(row)

    # design/169k K1 / 169i I3 — sample fingerprint when prior PNGs were preserved.
    if prior_fig_bytes and fig_meta:
        try:
            from sentence_reading.llm.artifact_ids import emit_artifact_observe, hash16_file

            preserved = [r for r in fig_meta if r.get("file")]
            if preserved:
                rel = str(preserved[0].get("file") or "")
                fp = fig_dir / rel.split("/")[-1] if rel else None
                h16, bn = hash16_file(fp) if fp else ("", 0)
                cid = str(cache_id or existing_id or "")
                if h16 and rel:
                    emit_artifact_observe(
                        activity="vision_write_figure",
                        cache_id=cid,
                        artifact_kind="figure_png",
                        locator=f"local:papers/{cid}/{rel}",
                        content_hash=h16,
                        bytes_n=bn,
                        ok=True,
                        extra={
                            "preserved_n": len(preserved),
                            "prior_png": len(prior_fig_bytes),
                            "fig_fingerprint": h16,
                        },
                    )
        except Exception:  # noqa: BLE001
            pass

    # design/168b — log-only T9/T11 (session figures vs written meta); never block save.
    try:
        from sentence_reading.llm.ingest_integrity import (
            check_fig_meta,
            check_figure_file_rel,
            emit_violations,
        )

        emit_violations(
            check_fig_meta(len(session.figures), len(fig_meta))
            + check_figure_file_rel(fig_meta),
            cache_id=cache_id,
            content_hash=ch or "",
        )
    except Exception:  # noqa: BLE001
        pass

    has_source = False
    source_rel: str | None = None
    if source_path is not None:
        try:
            sp = Path(source_path)
            if sp.is_file():
                size = sp.stat().st_size
                if 0 < size <= SOURCE_MAX_BYTES:
                    source_rel = source_filename_for(src)
                    shutil.copy2(sp, paper_dir / source_rel)
                    has_source = True
        except OSError:
            has_source = False
            source_rel = None

    has_tr = bool(session.translate_digests) or any(
        (s.text_ko or "").strip() for s in session.sentences
    ) or any((f.caption_ko or "").strip() for f in session.figures)

    payload = {
        "version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "title": title,
        "title_key": key,
        "source": src,
        "doc_role": role,
        "debone": bool(debone),
        "created_at": created_at,
        "saved_at": now,
        "figure_index": session.figure_index,
        "sentence_index": session.sentence_index,
        "has_source": has_source,
        "source_file": source_rel,
        "content_hash": ch or None,
        "supplementary_merged": bool(supplementary_merged),
        "supplementary_cache_id": (supplementary_cache_id or None),
        "merge_revision": merge_revision,
        "warnings": list(dict.fromkeys(warnings or [])),
        "ingest_quality": ingest_quality if isinstance(ingest_quality, dict) else {},
        "sentences": [
            {
                "id": s.id,
                "text": s.text,
                "section": s.section,
                "text_ko": s.text_ko or "",
                "text_ko_stage": s.text_ko_stage or "",
                **(
                    {"quality_flags": list(s.quality_flags)}
                    if s.quality_flags
                    else {}
                ),
            }
            for s in session.sentences
        ],
        "figures": fig_meta,
        "translate_digests": {
            str(k): {
                "en": str((v or {}).get("en") or ""),
                "ko": str((v or {}).get("ko") or ""),
            }
            for k, v in (session.translate_digests or {}).items()
            if isinstance(v, dict)
        },
        "references": _load_references(session.references),
        "document_citation": _load_document_citation(session.document_citation),
    }
    if has_tr:
        payload["translate_doc_version"] = "doc-v1"
    # design/169i — session generation for artifact ledger (metadata only).
    try:
        from sentence_reading.llm.artifact_ids import next_session_gen

        art_gen = next_session_gen(prior_meta_for_gen)
    except Exception:  # noqa: BLE001
        art_gen = 1
    payload["artifact_gen"] = int(art_gen)
    session_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (paper_dir / _SESSION_NAME).write_text(session_text, encoding="utf-8")
    # design/169i I1 — local write + derive (no paper text).
    try:
        from sentence_reading.llm import artifact_ids as aid

        parent = (
            aid.artifact_id_session(cache_id, art_gen - 1) if art_gen > 1 else ""
        )
        h16 = aid.hash16(session_text)
        child = aid.artifact_id_session(cache_id, art_gen)
        aid.emit_artifact_derive(
            activity="local_write_session",
            child_id=child,
            parent_ids=[parent] if parent else None,
            gen=art_gen,
            content_hash=h16,
            cache_id=cache_id,
        )
        aid.emit_artifact_transfer(
            activity="local_write_session",
            from_locator="mem:save",
            to_locator=aid.locator_local_session(cache_id),
            artifact_kind="session_json",
            content_hash=h16,
            bytes_n=len(session_text.encode("utf-8")),
            gen=art_gen,
            agent="cloud_run",
            ok=True,
            cache_id=cache_id,
            extra={"artifact_id": child},
        )
    except Exception:  # noqa: BLE001
        pass

    if forced:
        save_activity = "reanalyze"
    elif merge_revision is not None:
        save_activity = "merge_session"
    elif has_tr and existing_id:
        save_activity = "translate_save"
    else:
        save_activity = "ingest_store"
    preserved_n = decoded_src_n + preserved_from_prior_n
    _emit_figure_meta_boundary(
        cache_id=cache_id,
        art_gen=int(art_gen),
        activity=save_activity,
        session_fig_n=len(session.figures or []),
        fig_meta=fig_meta,
        prior_png_n=len(prior_fig_bytes),
        decoded_src_n=decoded_src_n,
        preserved_n=preserved_n,
        prior_meta_for_gen=prior_meta_for_gen,
        forced=bool(forced),
        content_hash=ch or "",
    )

    new_entry = {
        "id": cache_id,
        "title": title,
        "title_key": key,
        "source": src,
        "doc_role": role,
        "created_at": created_at,
        "updated_at": now,
        "sentence_count": len(session.sentences),
        "figure_count": len(fig_meta),
        "debone": bool(debone),
        "pipeline_version": PIPELINE_VERSION,
        "has_source": has_source,
        "content_hash": ch or None,
        "ingest_status": status,
        "supplementary_merged": bool(supplementary_merged),
        "merged_supplementary_id": (supplementary_cache_id or None),
        "hidden_in_library": False,
    }
    # design/169o — ProgressiveWriter / residual durable saves must not wipe
    # library banner fields from a prior patch_index_entry.
    for entry in entries:
        if not (isinstance(entry, dict) and entry.get("id") == cache_id):
            continue
        for hk in (
            "harmonize_pending",
            "harmonize_total",
            "harmonize_done",
            "harmonize_failed",
            "harmonize_attempt_n",
        ):
            if hk in entry:
                new_entry[hk] = entry[hk]
        break
    # design/168b — T4/T5 vs in-memory session counts (payload figures may already be truncated).
    try:
        from sentence_reading.llm.ingest_integrity import (
            check_session_vs_index,
            emit_violations,
        )

        synth = {
            "figures": [{"id": getattr(f, "id", "")} for f in session.figures],
            "sentences": payload.get("sentences") or [],
        }
        emit_violations(
            check_session_vs_index(synth, new_entry),
            cache_id=cache_id,
            content_hash=ch or "",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        from sentence_reading.llm.paper_retention import (
            reset_retention_on_save,
            retention_enabled,
        )

        if retention_enabled():
            new_entry.update(reset_retention_on_save())
            new_entry.pop("reading_grace_from", None)
            new_entry.pop("last_extended_at", None)
    except Exception:
        pass
    entries = [e for e in entries if not (isinstance(e, dict) and e.get("id") == cache_id)]
    entries = [
        e
        for e in entries
        if not (
            isinstance(e, dict)
            and e.get("title_key") == key
            and str(e.get("source") or "pdf").lower() == src
            and str(e.get("doc_role") or "main").strip().lower() == role
        )
    ]
    entries.insert(0, new_entry)
    index["entries"] = _evict_oldest(entries, keep=_MAX_CACHED_PAPERS)
    _write_index(index)
    if layout_artifacts:
        save_layout_artifacts(
            paper_dir,
            layout_map=layout_artifacts.get("layout_map"),
            slot_plan=layout_artifacts.get("slot_plan"),
            prior_slot_plan=prior_slot_plan,
        )
    # WHY: 보관 직후 GCS push — Live에서는 index 등재까지 확인 (design/174).
    try:
        from sentence_reading.llm.auth_google import auth_enabled
        from sentence_reading.llm.papers_gcs import (
            ensure_paper_in_remote_index,
            gcs_papers_ready,
            upload_paper_cache,
        )

        if gcs_papers_ready() and auth_enabled():
            new_entry["_gcs_listed"] = bool(
                ensure_paper_in_remote_index(cache_id, retries=1)
            )
        else:
            upload_paper_cache(cache_id)
            new_entry["_gcs_listed"] = True
    except Exception:  # noqa: BLE001
        try:
            from sentence_reading.llm.auth_google import auth_enabled
            from sentence_reading.llm.papers_gcs import gcs_papers_ready

            if gcs_papers_ready() and auth_enabled():
                new_entry["_gcs_listed"] = False
        except Exception:  # noqa: BLE001
            pass
    # design/169d — sample save boundary (no paper text).
    try:
        import random

        if random.randint(1, 5) == 1:
            from sentence_reading.llm import evidence_bus as eb

            with_file = sum(1 for row in fig_meta if str(row.get("file") or "").strip())
            eb.emit(
                "cache_save_sample",
                severity="sample",
                cache_id=str(cache_id or ""),
                content_hash=str(ch or ""),
                stage="save",
                details={
                    "fig_meta_n": len(fig_meta),
                    "with_file_n": int(with_file),
                    "sentence_n": len(session.sentences or []),
                    "forced": 1 if forced else 0,
                },
                ok=True,
                code="cache_save_sample",
            )
    except Exception:  # noqa: BLE001
        pass
    return new_entry
