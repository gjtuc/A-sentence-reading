"""
design/152 — append SI session into main cache entry.
"""

from __future__ import annotations

from sentence_reading.cache.paper_cache import (
    _read_index,
    cache_root,
    load_cached_session,
    patch_index_entry,
    save_paper_session,
)
from sentence_reading.cache.supplementary_library import (
    apply_pairing_pass,
    can_merge_supplementary,
)
from sentence_reading.models import Figure, PaperSession, Sentence


def merge_supplementary(main_id: str) -> dict:
    """Merge paired SI into main; returns API result dict."""
    cid = (main_id or "").strip()
    if not cid:
        return {"ok": False, "error": "bad_cache_id", "message": "잘못된 보관 id입니다."}

    entries = [dict(e) for e in _read_index().get("entries") or [] if isinstance(e, dict)]
    apply_pairing_pass(entries)
    main_entry = next((e for e in entries if e.get("id") == cid), None)
    if main_entry is None:
        return {
            "ok": False,
            "error": "cache_not_found",
            "message": "보관된 논문을 찾을 수 없습니다.",
        }
    if not can_merge_supplementary(main_entry, entries):
        return {
            "ok": False,
            "error": "merge_not_allowed",
            "message": "보충자료를 합칠 수 없습니다. 본문·보충이 모두 준비됐는지 확인해 주세요.",
        }

    si_id = str(main_entry.get("paired_cache_id") or "").strip()
    main_loaded = load_cached_session(cid, load_images=True)
    si_loaded = load_cached_session(si_id, load_images=True)
    if main_loaded is None or si_loaded is None:
        return {
            "ok": False,
            "error": "session_missing",
            "message": "세션을 불러오지 못했습니다.",
        }
    main_session, _ = main_loaded
    si_session, _ = si_loaded

    used_ids: set[str] = {s.id for s in main_session.sentences}
    appended_sentences: list[Sentence] = []
    for i, s in enumerate(si_session.sentences):
        sid = s.id
        if sid in used_ids or not sid:
            sid = f"si_{i + 1:04d}"
            n = 0
            while sid in used_ids:
                n += 1
                sid = f"si_{i + 1:04d}_{n}"
        used_ids.add(sid)
        appended_sentences.append(
            Sentence(
                id=sid,
                text=s.text,
                section="supplementary",
                start_char=s.start_char,
                end_char=s.end_char,
                text_ko=s.text_ko or "",
                text_ko_stage=s.text_ko_stage or "",
            )
        )

    main_dir = cache_root() / cid
    src_path = main_dir / "source.pdf"

    merged_figures = list(main_session.figures)
    for i, fig in enumerate(si_session.figures):
        new_id = fig.id or f"si-fig-{len(merged_figures) + i + 1:04d}"
        if not str(new_id).startswith("si-"):
            new_id = f"si-{new_id}"
        merged_figures.append(
            Figure(
                id=new_id,
                image_src=fig.image_src,
                caption=fig.caption,
                page_index=fig.page_index,
                slot_key=fig.slot_key or "",
                caption_ko=fig.caption_ko or "",
                caption_ko_stage=fig.caption_ko_stage or "",
            )
        )

    merged_session = PaperSession(
        title=main_session.title,
        figures=merged_figures,
        sentences=list(main_session.sentences) + appended_sentences,
        figure_index=main_session.figure_index,
        sentence_index=main_session.sentence_index,
        translate_digests={
            **(main_session.translate_digests or {}),
            **(si_session.translate_digests or {}),
        },
        references=main_session.references or si_session.references,
    )
    merged_session.clamp_indices()

    rev = int(main_entry.get("merge_revision") or 0) + 1
    if not src_path.is_file():
        src_path = main_dir / "source.docx"
    if not src_path.is_file():
        src_path = None

    entry = save_paper_session(
        merged_session,
        debone=bool(main_entry.get("debone")),
        source=str(main_entry.get("source") or "pdf"),
        doc_role="merged",
        source_path=src_path,
        content_hash=str(main_entry.get("content_hash") or "") or None,
        supplementary_merged=True,
        supplementary_cache_id=si_id,
        merge_revision=rev,
    )
    if entry is None:
        return {
            "ok": False,
            "error": "merge_save_failed",
            "message": "합친 결과를 저장하지 못했습니다.",
        }

    patch_index_entry(si_id, hidden_in_library=True)
    patch_index_entry(
        cid,
        doc_role="merged",
        supplementary_merged=True,
        merged_supplementary_id=si_id,
        merge_revision=rev,
        ingest_status="ok",
    )

    try:
        from sentence_reading.llm.papers_gcs import upload_paper_cache

        upload_paper_cache(cid)
        upload_paper_cache(si_id)
    except Exception:
        pass

    return {
        "ok": True,
        "cache_id": cid,
        "merged_supplementary_id": si_id,
        "sentence_count": len(merged_session.sentences),
        "figure_count": len(merged_session.figures),
        "library_tag": "메인+서플먼터리",
    }
