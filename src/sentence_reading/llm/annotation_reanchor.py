"""
Reanchor user annotations after re-debone (design/166 · 167).

Priority:
1. sentence_id + text similarity >= threshold
2. bookmark key still valid in new nav
3. TextQuoteSelector fuzzy match
4. orphaned
"""

from __future__ import annotations

import re
from typing import Any

from sentence_reading.llm.richtext import plain_text

SIMILARITY_THRESHOLD = 0.85


def _token_set(text: str) -> set[str]:
    plain = plain_text(text).lower()
    return set(re.findall(r"[a-z0-9]{3,}", plain))


def texts_similar(a: str, b: str) -> float:
    ta = _token_set(a)
    tb = _token_set(b)
    if not ta or not tb:
        return 1.0 if plain_text(a).strip() == plain_text(b).strip() else 0.0
    inter = len(ta & tb)
    denom = max(len(ta), len(tb))
    return inter / denom if denom else 0.0


def _selector_match(
    selector: dict[str, Any] | None, sentences: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not isinstance(selector, dict):
        return None
    exact = str(selector.get("exact") or "").strip()
    if not exact:
        return None
    prefix = str(selector.get("prefix") or "")
    suffix = str(selector.get("suffix") or "")
    needle = plain_text(exact).lower()
    for s in sentences:
        text = plain_text(str(s.get("text") or ""))
        low = text.lower()
        if needle and needle in low:
            if prefix and prefix not in text:
                continue
            if suffix and suffix not in text:
                continue
            return s
    return None


def reanchor_annotation_event(
    ev: dict[str, Any],
    *,
    sentences: list[dict[str, Any]],
    sentence_by_id: dict[str, dict[str, Any]],
    valid_keys: set[str],
    key_to_sentence_id: dict[str, str],
) -> dict[str, Any]:
    """Return updated event with status when reanchored or orphaned."""
    out = dict(ev)
    sid = str(ev.get("sentence_id") or "").strip()
    old_text = ""
    if sid and sid in sentence_by_id:
        old_text = str(sentence_by_id[sid].get("text") or "")

    # Pass 1 — same sentence_id with similar text
    if sid and sid in sentence_by_id:
        new_row = sentence_by_id[sid]
        new_text = str(new_row.get("text") or "")
        if texts_similar(old_text or new_text, new_text) >= SIMILARITY_THRESHOLD:
            out["status"] = "ok"
            return out

    # Pass 2 — bookmark key from event metadata or infer from sentence_id map
    bookmark_key = str(ev.get("bookmark_key") or "").strip()
    if not bookmark_key:
        for k, mapped_sid in key_to_sentence_id.items():
            if mapped_sid == sid:
                bookmark_key = k
                break
    if bookmark_key and bookmark_key in valid_keys:
        new_sid = key_to_sentence_id.get(bookmark_key, sid)
        out["sentence_id"] = new_sid
        out["status"] = "reanchored_by_key"
        return out

    # Pass 3 — TextQuoteSelector
    sel = ev.get("selector")
    if isinstance(sel, dict):
        hit = _selector_match(sel, sentences)
        if hit is not None:
            out["sentence_id"] = str(hit.get("id") or "")
            out["status"] = "reanchored_by_selector"
            return out

    out["status"] = "orphaned"
    return out


def reanchor_paper_annotations(
    paper: dict[str, Any],
    *,
    sentences: list[dict[str, Any]],
    valid_sentence_keys: set[str],
    key_to_sentence_id: dict[str, str],
) -> dict[str, Any]:
    sentence_by_id = {
        str(s.get("id") or ""): s for s in sentences if isinstance(s, dict)
    }
    out = {"sentences": {}, "figures": paper.get("figures") or {}}
    raw_sentences = paper.get("sentences")
    if not isinstance(raw_sentences, dict):
        return out
    for key, events in raw_sentences.items():
        if not isinstance(key, str) or not isinstance(events, list):
            continue
        updated: list[dict[str, Any]] = []
        for raw in events:
            if not isinstance(raw, dict):
                continue
            ev = reanchor_annotation_event(
                raw,
                sentences=sentences,
                sentence_by_id=sentence_by_id,
                valid_keys=valid_sentence_keys,
                key_to_sentence_id=key_to_sentence_id,
            )
            updated.append(ev)
        if updated:
            out["sentences"][key] = updated
    return out
