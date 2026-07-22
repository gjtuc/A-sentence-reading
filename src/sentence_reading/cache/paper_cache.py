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


def find_cached_by_text(text: str, *, source: str = "pdf") -> dict | None:
    """
    원문 앞부분에 캐시된 논문 제목이 들어 있으면 그 entry 반환.
    source(pdf/docx)가 같은 항목만 — 본편·보충자료 제목 충돌 방지.
    가장 긴 title_key 일치를 고른다.
    """
    if not (text or "").strip():
        return None
    head = normalize_title_key(text[:_HEAD_CHARS])
    if len(head) < _MIN_TITLE_KEY_LEN:
        return None
    want = (source or "pdf").lower()

    best: dict | None = None
    best_len = 0
    for entry in _read_index().get("entries", []):
        if not isinstance(entry, dict):
            continue
        # 구버전 캐시(source 없음)는 pdf 로 간주
        entry_src = str(entry.get("source") or "pdf").lower()
        if entry_src != want:
            continue
        key = str(entry.get("title_key") or "")
        if len(key) < _MIN_TITLE_KEY_LEN:
            continue
        if key in head and len(key) > best_len:
            best = entry
            best_len = len(key)
    return best


def _delete_paper_dir(cache_id: str) -> None:
    import shutil

    path = cache_root() / cache_id
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def delete_cached_paper(
    *,
    cache_id: str | None = None,
    title: str | None = None,
    source: str | None = None,
) -> dict | None:
    """
    보관본 삭제. cache_id 우선, 없으면 title+source 로 찾음.
    반환: 삭제된 entry 또는 None.
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
            # title_key 없을 때 제목 문자열 직접 비교
            if normalize_title_key(str(e.get("title") or "")) == key and entry_src == src:
                target = e
                break

    if target is None:
        return None

    tid = str(target.get("id") or "")
    if tid:
        _delete_paper_dir(tid)
    index["entries"] = [
        e for e in entries if not (isinstance(e, dict) and e.get("id") == tid)
    ]
    _write_index(index)
    return target



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


def list_cached_papers() -> list[dict]:
    entries = []
    for entry in _read_index().get("entries", []):
        if not isinstance(entry, dict):
            continue
        cid = entry.get("id")
        title = entry.get("title")
        if not cid or not title:
            continue
        entries.append(
            {
                "id": cid,
                "title": title,
                "source": str(entry.get("source") or "pdf"),
                "updated_at": entry.get("updated_at") or "",
                "sentence_count": int(entry.get("sentence_count") or 0),
                "figure_count": int(entry.get("figure_count") or 0),
                "debone": bool(entry.get("debone")),
            }
        )
    entries.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    return entries


def load_cached_session(cache_id: str) -> tuple[PaperSession, dict] | None:
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
        )
        for i, s in enumerate(meta.get("sentences") or [])
        if isinstance(s, dict) and str(s.get("text") or "").strip()
    ]

    figures: list[Figure] = []
    for i, f in enumerate(meta.get("figures") or []):
        if not isinstance(f, dict):
            continue
        rel = f.get("file")
        if not rel:
            continue
        img_path = root / str(rel)
        if not img_path.is_file():
            continue
        try:
            src = _figure_to_data_url(img_path)
        except OSError:
            continue
        figures.append(
            Figure(
                id=str(f.get("id") or f"fig-{i + 1:04d}"),
                image_src=src,
                caption=str(f.get("caption") or ""),
                page_index=f.get("page_index"),
            )
        )

    title = str(meta.get("title") or "Untitled")
    session = PaperSession(
        title=title,
        figures=figures,
        sentences=sentences,
        figure_index=int(meta.get("figure_index") or 0),
        sentence_index=int(meta.get("sentence_index") or 0),
    )
    session.clamp_indices()
    info = {
        "cache_id": cache_id,
        "debone": bool(meta.get("debone")),
        "from_cache": True,
    }
    return session, info


def save_paper_session(
    session: PaperSession,
    *,
    debone: bool = False,
    source: str = "pdf",
) -> dict | None:
    """
    제목 키 + source(pdf/docx) 로 저장.
    같은 제목이어도 본편 PDF 와 보충 Word 는 서로 덮어쓰지 않음.
    """
    title = (session.title or "").strip()
    key = normalize_title_key(title)
    if len(key) < _MIN_TITLE_KEY_LEN:
        return None
    if not session.sentences:
        return None
    src = (source or "pdf").lower()
    if src not in ("pdf", "docx"):
        src = "pdf"

    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)

    index = _read_index()
    entries: list = index.setdefault("entries", [])
    existing_id = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_src = str(entry.get("source") or "pdf").lower()
        if entry.get("title_key") == key and entry_src == src:
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
    if paper_dir.exists():
        # 옛 그림 정리 후 재기록
        import shutil

        shutil.rmtree(paper_dir, ignore_errors=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig_meta: list[dict] = []
    for i, fig in enumerate(session.figures):
        decoded = _decode_data_url(fig.image_src)
        if not decoded:
            continue
        raw, ext = decoded
        fname = f"{fig.id or f'fig-{i + 1:04d}'}.{ext}"
        # 경로 안전
        fname = re.sub(r"[^\w.\-]+", "_", fname)
        (fig_dir / fname).write_bytes(raw)
        fig_meta.append(
            {
                "id": fig.id,
                "caption": fig.caption,
                "page_index": fig.page_index,
                "file": f"figures/{fname}",
            }
        )

    payload = {
        "version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "title": title,
        "title_key": key,
        "source": src,
        "debone": bool(debone),
        "created_at": created_at,
        "saved_at": now,
        "figure_index": session.figure_index,
        "sentence_index": session.sentence_index,
        "sentences": [
            {"id": s.id, "text": s.text, "section": s.section} for s in session.sentences
        ],
        "figures": fig_meta,
    }
    (paper_dir / _SESSION_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    new_entry = {
        "id": cache_id,
        "title": title,
        "title_key": key,
        "source": src,
        "created_at": created_at,
        "updated_at": now,
        "sentence_count": len(session.sentences),
        "figure_count": len(fig_meta),
        "debone": bool(debone),
        "pipeline_version": PIPELINE_VERSION,
    }
    entries = [e for e in entries if not (isinstance(e, dict) and e.get("id") == cache_id)]
    entries = [
        e
        for e in entries
        if not (
            isinstance(e, dict)
            and e.get("title_key") == key
            and str(e.get("source") or "pdf").lower() == src
        )
    ]
    entries.insert(0, new_entry)
    index["entries"] = _evict_oldest(entries, keep=_MAX_CACHED_PAPERS)
    _write_index(index)
    return new_entry
