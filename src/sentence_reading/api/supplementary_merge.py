"""
design/152 — append SI session into main cache entry.
design/492 — any document can be attached behind a paper, several in order.
"""

from __future__ import annotations

from sentence_reading.cache.paper_cache import (
    _read_index,
    cache_root,
    load_cached_session,
    patch_index_entry,
    save_paper_session,
)
from sentence_reading.cache.doc_parts import (
    figure_prefix,
    merged_tag,
    normalize_parts,
    prior_parts,
    sentence_prefix,
)
from sentence_reading.cache.supplementary_library import (
    _ingest_ok,
    apply_pairing_pass,
    can_merge_supplementary,
    entry_doc_role,
)
from sentence_reading.models import Figure, PaperSession, Sentence


def _index_entries_with_remote() -> list[dict]:
    """Local index rows plus the signed-in user's GCS index rows.

    design/468 — the library list is local ∪ GCS, but a fresh Cloud Run
    instance holds only the papers it analyzed itself. Reading the local index
    alone answered ``cache_not_found`` for papers the user could see.
    """
    local = [dict(e) for e in _read_index().get("entries") or [] if isinstance(e, dict)]
    try:
        from sentence_reading.llm import papers_gcs as pg

        if not (pg.gcs_papers_ready() and pg.papers_index_object()):
            return local
        remote = pg.download_remote_index().get("entries") or []
    except Exception:  # noqa: BLE001
        return local
    remote_ids = {e.get("id") for e in remote if isinstance(e, dict)}
    mine = [e for e in local if e.get("id") in remote_ids]
    return [dict(e) for e in pg.merge_index_entries(mine, remote)]


def _pull_from_gcs(entries: list[dict], ids: tuple[str, ...]) -> None:
    """Overwrite the instance copy from the user's GCS prefix (design/121 rule)."""
    try:
        from sentence_reading.llm import papers_gcs as pg

        if not pg.gcs_papers_ready():
            return
        by_id = {str(e.get("id") or ""): e for e in entries}
        for i in ids:
            if i:
                pg.download_paper_cache(i, entry=by_id.get(i))
    except Exception:  # noqa: BLE001
        return


def merge_supplementary(main_id: str) -> dict:
    """Merge paired SI into main; returns API result dict."""
    cid = (main_id or "").strip()
    if not cid:
        return {"ok": False, "error": "bad_cache_id", "message": "잘못된 보관 id입니다."}

    entries = _index_entries_with_remote()
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
    return _attach(cid, main_entry, entries, [{"id": si_id, "section": "supplementary"}])


def attach_parts(main_id: str, parts: object) -> dict:
    """design/492 — attach [parts] (``[{"id", "section"}]``) behind [main_id], in order.

    Parts already inside the paper are skipped, so a repeat press is harmless.
    """
    cid = (main_id or "").strip()
    if not cid:
        return {"ok": False, "error": "bad_cache_id", "message": "잘못된 보관 id입니다."}
    wanted = [p for p in normalize_parts(parts) if p["id"] != cid]
    if not wanted:
        return {"ok": False, "error": "bad_parts", "message": "붙일 문서가 없습니다."}
    entries = _index_entries_with_remote()
    apply_pairing_pass(entries)
    main_entry = next((e for e in entries if e.get("id") == cid), None)
    if main_entry is None:
        return {
            "ok": False,
            "error": "cache_not_found",
            "message": "보관된 논문을 찾을 수 없습니다.",
        }
    if entry_doc_role(main_entry) == "supplementary" or not _ingest_ok(main_entry):
        return {
            "ok": False,
            "error": "merge_not_allowed",
            "message": "이 문서 뒤에는 붙일 수 없습니다.",
        }
    return _attach(cid, main_entry, entries, wanted)


def _attach(cid: str, main_entry: dict, entries: list[dict], parts: list[dict]) -> dict:
    prior = prior_parts(main_entry)
    prior_ids = {p["id"] for p in prior}
    new = [p for p in parts if p["id"] and p["id"] != cid and p["id"] not in prior_ids]
    if not new:
        return {
            "ok": True,
            "already": True,
            "cache_id": cid,
            "merged_parts": prior,
            "library_tag": merged_tag([p["section"] for p in prior]),
        }
    by_id = {str(e.get("id") or ""): e for e in entries if isinstance(e, dict)}
    for p in new:
        pe = by_id.get(p["id"])
        if pe is None:
            return {
                "ok": False,
                "error": "cache_not_found",
                "message": "붙일 문서를 찾을 수 없습니다.",
            }
        if entry_doc_role(pe) == "merged" or not _ingest_ok(pe):
            return {
                "ok": False,
                "error": "merge_not_allowed",
                "message": "합친 문서나 분석 중인 문서는 붙일 수 없습니다.",
            }

    _pull_from_gcs(entries, (cid, *[p["id"] for p in new]))
    main_loaded = load_cached_session(cid, load_images=True)
    part_sessions = []
    for p in new:
        loaded = load_cached_session(p["id"], load_images=True)
        if loaded is None:
            main_loaded = None
            break
        part_sessions.append(loaded[0])
    if main_loaded is None:
        return {
            "ok": False,
            "error": "session_missing",
            "message": "세션을 불러오지 못했습니다.",
        }
    main_session, _ = main_loaded

    from sentence_reading.cite_refs import filter_bibliography_sentences

    merge_refs = main_session.references
    if not merge_refs:
        merge_refs = next((s.references for s in part_sessions if s.references), None)
    refs_list = merge_refs if isinstance(merge_refs, list) else []

    used_ids: set[str] = {s.id for s in main_session.sentences}
    appended_sentences: list[Sentence] = []
    merged_figures = list(main_session.figures)
    used_fig_ids: set[str] = {str(f.id or "") for f in merged_figures}
    digests = dict(main_session.translate_digests or {})
    for p, part in zip(new, part_sessions):
        section = p["section"]
        sp = sentence_prefix(section)
        for i, s in enumerate(filter_bibliography_sentences(list(part.sentences), refs_list)):
            sid = s.id
            if sid in used_ids or not sid:
                sid = f"{sp}{i + 1:04d}"
                n = 0
                while sid in used_ids:
                    n += 1
                    sid = f"{sp}{i + 1:04d}_{n}"
            used_ids.add(sid)
            appended_sentences.append(
                Sentence(
                    id=sid,
                    text=s.text,
                    section=section,
                    start_char=s.start_char,
                    end_char=s.end_char,
                    text_ko=s.text_ko or "",
                    text_ko_stage=s.text_ko_stage or "",
                    # design/321 — rebuilding without this erased the ungrounded mark,
                    # so merged papers were the one place the badge could not appear.
                    quality_flags=getattr(s, "quality_flags", ()) or (),
                    equations=getattr(s, "equations", ()) or (),
                )
            )
        fp = figure_prefix(section)
        for i, fig in enumerate(part.figures):
            base = str(fig.id or f"fig-{len(merged_figures) + i + 1:04d}")
            new_id = base if base.startswith(fp) else f"{fp}{base}"
            n = 1
            while new_id in used_fig_ids:
                n += 1
                new_id = f"{fp}{n}-{base}"
            used_fig_ids.add(new_id)
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
        digests.update(part.translate_digests or {})

    merged_session = PaperSession(
        title=main_session.title,
        figures=merged_figures,
        sentences=list(main_session.sentences) + appended_sentences,
        figure_index=main_session.figure_index,
        sentence_index=main_session.sentence_index,
        translate_digests=digests,
        references=merge_refs,
        document_citation=dict(main_session.document_citation or {}),
        headings=list(main_session.headings or []),
    )
    merged_session.clamp_indices()

    all_parts = prior + new
    si_id = next((p["id"] for p in all_parts if p["section"] == "supplementary"), "")
    main_dir = cache_root() / cid
    src_path = main_dir / "source.pdf"
    rev = int(main_entry.get("merge_revision") or 0) + 1
    if not src_path.is_file():
        src_path = main_dir / "source.docx"
    if not src_path.is_file():
        src_path = None

    # design/218/152 — role flips main→merged; without force_cache_id save
    # allocates a new id and the patched main row keeps the pre-merge session.
    entry = save_paper_session(
        merged_session,
        debone=bool(main_entry.get("debone")),
        source=str(main_entry.get("source") or "pdf"),
        doc_role="merged",
        source_path=src_path,
        content_hash=str(main_entry.get("content_hash") or "") or None,
        supplementary_merged=True,
        supplementary_cache_id=si_id or None,
        merge_revision=rev,
        force_cache_id=cid,
    )
    if entry is None:
        return {
            "ok": False,
            "error": "merge_save_failed",
            "message": "합친 결과를 저장하지 못했습니다.",
        }

    for p in new:
        patch_index_entry(p["id"], hidden_in_library=True)
    patch_index_entry(
        cid,
        doc_role="merged",
        supplementary_merged=True,
        merged_supplementary_id=si_id or None,
        merged_parts=all_parts,
        merge_revision=rev,
        ingest_status="ok",
    )

    try:
        from sentence_reading.llm.papers_gcs import upload_paper_cache

        upload_paper_cache(cid)
        for p in new:
            upload_paper_cache(p["id"])
    except Exception:
        pass

    return {
        "ok": True,
        "cache_id": cid,
        "merged_supplementary_id": si_id,
        "merged_parts": all_parts,
        "sentence_count": len(merged_session.sentences),
        "figure_count": len(merged_session.figures),
        "library_tag": merged_tag([p["section"] for p in all_parts]),
    }
