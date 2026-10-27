"""design/469 — the paper's own headings, stored once per paper.

Sentences carry a section key from a fixed vocabulary (introduction, body, …), so a
review paper with free headings read as one long `body`. The heading text is kept in
one list per paper, `[{"text": "2.1. Metal-Metal Interactions", "from": "sent_000047"}]`.
Each entry starts at the sentence `from` and runs until the next entry, so a sentence
needs no field of its own. An entry with empty text ends the previous heading.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from sentence_reading.pdf.box_marks import BoxMark, assign_boxes

_MAX_HEADINGS = 200
_NO_HEADING_SECTIONS = frozenset({"title", "supplementary", "references"})


def _letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"<[^>]+>", "", text or "").lower())


def heading_anchors(
    sentences: Iterable, marks: list[BoxMark], *, title: str = ""
) -> list[dict[str, str]]:
    """Heading starts for `sentences`, from the boxes the sentences came from.

    A heading printed inside a card is sought by the text right after it, as a mark of
    its own. These marks exist only here; the boxes debone placed sentences with are
    not changed.
    """
    rows = list(sentences)
    if not rows or not marks or not any(m.heading or m.heading_starts for m in marks):
        return []
    probes: list[BoxMark] = []
    for m in marks:
        own = _letters(m.openings[0]) if m.openings else ""
        # `Metrics & More CONSPECTUS: In recent years…` — chrome glued in front of a
        # heading. The card's opening then names the heading's first sentence too, and
        # finding it there would leave the heading nothing to find.
        if not any(own and _letters(o[0])[:30] in own for _h, o in m.heading_starts):
            probes.append(m)
        for head, openings in m.heading_starts:
            probes.append(
                replace(
                    m,
                    marker=openings[0],
                    openings=openings,
                    continues_previous=False,
                    heading=head,
                    heading_starts=(),
                )
            )
    owner, _census = assign_boxes(probes, [getattr(s, "text", "") or "" for s in rows])
    title_key = _letters(title)
    out: list[dict[str, str]] = []
    current = ""
    for s, p_i in zip(rows, owner):
        sid = str(getattr(s, "id", "") or "")
        if not sid:
            continue
        if (getattr(s, "section", "") or "") in _NO_HEADING_SECTIONS:
            head = ""
        else:
            head = probes[p_i].heading if p_i >= 0 else current
            if title_key and _letters(head) == title_key:
                head = ""
        if head != current:
            out.append({"text": head, "from": sid})
            current = head
    return clean_headings(out)


def clean_headings(raw: object) -> list[dict[str, str]]:
    """Stored or received headings, bounded and shaped."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for row in raw[:_MAX_HEADINGS]:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("from") or "").strip()[:64]
        if not sid:
            continue
        text = " ".join(str(row.get("text") or "").split())[:200]
        out.append({"text": text, "from": sid})
    while out and not out[0]["text"]:
        out.pop(0)
    return out


def stored_headings(cache_id: str) -> tuple[list[dict[str, str]], str]:
    """design/470 — the saved list of one paper, for a device copy that lacks it.

    Read from the signed-in user's GCS session only; the shared instance disk can hold
    another user's leftover (design/121). Local disk only when GCS is off.
    """
    import json

    from sentence_reading.cache.paper_cache import _SESSION_NAME, cache_root
    from sentence_reading.llm import papers_gcs as pg
    from sentence_reading.llm.gcs_sync import download_bytes

    obj = pg.paper_session_object(cache_id)
    if not obj:
        return [], "bad_cache_id"
    if pg.gcs_papers_ready():
        raw = download_bytes(obj)
    else:
        path = cache_root() / cache_id.strip() / _SESSION_NAME
        raw = path.read_bytes() if path.is_file() else None
    if not raw:
        return [], "not_found"
    if len(raw) > pg.PAPER_SESSION_MAX_BYTES:
        return [], "too_large"
    try:
        meta = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [], "bad_session"
    if not isinstance(meta, dict):
        return [], "bad_session"
    return clean_headings(meta.get("headings")), "ok"
