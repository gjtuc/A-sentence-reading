"""
design/152 — library tags, pairing, merge eligibility for main/SI papers.
"""

from __future__ import annotations

from typing import Any

DocRole = str  # main | supplementary | merged

_LIBRARY_TAGS = {
    "main": "메인",
    "supplementary": "보충",
    "merged": "메인+서플먼터리",
}


def entry_doc_role(entry: dict[str, Any] | None) -> DocRole:
    if not isinstance(entry, dict):
        return "main"
    raw = str(entry.get("doc_role") or "main").strip().lower()
    if raw in ("supplementary", "si", "supp"):
        return "supplementary"
    if raw == "merged":
        return "merged"
    return "main"


def library_tag_for(entry: dict[str, Any]) -> str:
    return _LIBRARY_TAGS.get(entry_doc_role(entry), "메인")


def _ingest_ok(entry: dict[str, Any]) -> bool:
    return str(entry.get("ingest_status") or "ok").strip().lower() == "ok"


def _by_title_role(entries: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        key = str(e.get("title_key") or "")
        if not key:
            continue
        src = str(e.get("source") or "pdf").lower()
        role = entry_doc_role(e)
        out[(key, src, role)] = e
    return out


def apply_pairing_pass(entries: list[dict[str, Any]]) -> None:
    """Mutual paired_cache_id for same title_key main↔supplementary (1:1)."""
    mains: dict[tuple[str, str], dict[str, Any]] = {}
    sis: dict[tuple[str, str], dict[str, Any]] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        key = str(e.get("title_key") or "")
        if not key:
            continue
        src = str(e.get("source") or "pdf").lower()
        ts = (key, src)
        role = entry_doc_role(e)
        if role == "main":
            prev = mains.get(ts)
            if prev is None or str(e.get("updated_at") or "") >= str(
                prev.get("updated_at") or ""
            ):
                mains[ts] = e
        elif role == "supplementary":
            prev = sis.get(ts)
            if prev is None or str(e.get("updated_at") or "") >= str(
                prev.get("updated_at") or ""
            ):
                sis[ts] = e
    for ts, main_e in mains.items():
        si_e = sis.get(ts)
        if si_e is None:
            main_e.pop("paired_cache_id", None)
            continue
        main_e["paired_cache_id"] = str(si_e.get("id") or "")
        si_e["paired_cache_id"] = str(main_e.get("id") or "")


def can_merge_supplementary(main_entry: dict[str, Any], entries: list[dict[str, Any]]) -> bool:
    if entry_doc_role(main_entry) != "main":
        return False
    if main_entry.get("supplementary_merged"):
        return False
    if not _ingest_ok(main_entry):
        return False
    si_id = str(main_entry.get("paired_cache_id") or "").strip()
    if not si_id:
        return False
    for e in entries:
        if not isinstance(e, dict):
            continue
        if str(e.get("id") or "") != si_id:
            continue
        return entry_doc_role(e) == "supplementary" and _ingest_ok(e)
    return False


def enrich_paper_list_entry(
    entry: dict[str, Any],
    *,
    all_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """API-facing list row fields."""
    role = entry_doc_role(entry)
    row = dict(entry)
    row["doc_role"] = role
    row["library_tag"] = library_tag_for(entry)
    row["ingest_status"] = str(entry.get("ingest_status") or "ok")
    row["can_merge_supplementary"] = can_merge_supplementary(
        entry, all_entries or [entry]
    )
    return row


def list_entries_for_api(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairing pass + hide merged-away SI + enrich."""
    raw = [e for e in entries if isinstance(e, dict)]
    apply_pairing_pass(raw)
    visible = [e for e in raw if not e.get("hidden_in_library")]
    out: list[dict[str, Any]] = []
    for e in visible:
        cid = e.get("id")
        title = e.get("title")
        if not cid or not title:
            continue
        enriched = enrich_paper_list_entry(e, all_entries=raw)
        row = {
            "id": cid,
            "title": title,
            "source": str(enriched.get("source") or "pdf"),
            "updated_at": enriched.get("updated_at") or "",
            "sentence_count": int(enriched.get("sentence_count") or 0),
            "figure_count": int(enriched.get("figure_count") or 0),
            "debone": bool(enriched.get("debone")),
            "pipeline_version": str(enriched.get("pipeline_version") or ""),
            "has_source": bool(enriched.get("has_source")),
            "doc_role": enriched["doc_role"],
            "library_tag": enriched["library_tag"],
            "ingest_status": enriched["ingest_status"],
            "can_merge_supplementary": enriched["can_merge_supplementary"],
            "paired_cache_id": enriched.get("paired_cache_id"),
        }
        # design/169o — library banner polls these after ingest done.
        if enriched.get("harmonize_pending") is not None:
            row["harmonize_pending"] = bool(enriched.get("harmonize_pending"))
            try:
                row["harmonize_total"] = int(enriched.get("harmonize_total") or 0)
            except (TypeError, ValueError):
                row["harmonize_total"] = 0
            try:
                row["harmonize_done"] = int(enriched.get("harmonize_done") or 0)
            except (TypeError, ValueError):
                row["harmonize_done"] = 0
            try:
                row["harmonize_failed"] = int(enriched.get("harmonize_failed") or 0)
            except (TypeError, ValueError):
                row["harmonize_failed"] = 0
            try:
                row["harmonize_attempt_n"] = int(
                    enriched.get("harmonize_attempt_n") or 0
                )
            except (TypeError, ValueError):
                row["harmonize_attempt_n"] = 0
        out.append(row)
    return out
