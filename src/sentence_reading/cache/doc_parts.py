"""
design/492 - documents attached behind a paper, in order.

A merged paper keeps ``merged_parts``: ``[{"id", "section"}]``. The section says
what the part is in the reader (supplementary, review, attached) and fixes the
sentence/figure id prefixes, so a part never collides with the paper's own ids.

``file_article_key`` links a paper and its extra files by the article number in
their file names (``s41467-021-24079-8`` and ``41467_2021_24079_MOESM2``), which
is the only thing a peer review file shares with its paper.
"""

from __future__ import annotations

import re
from typing import Any

PART_SECTIONS = ("supplementary", "review", "attached")

_FIG_PREFIX = {"supplementary": "si-", "review": "rv-", "attached": "at-"}
_SENT_PREFIX = {"supplementary": "si_", "review": "rv_", "attached": "at_"}
_SECTION_TAGS = {"supplementary": "보충", "review": "심사", "attached": "첨부"}

_NATURE = re.compile(r"(?<!\d)s?(\d{5})[-_](\d{3,4})[-_](\d{5})(?!\d)")
_PART_MARK = re.compile(
    r"[-_ .](?:si|sup|supp|suppl|supporting|supplement|supplementary|esm|moesm\d*"
    r"|mmc\d*|main|appendix|peer[-_ ]?review|review|reviews|reviewer)(?![a-z])"
)
_EXT = re.compile(r"\.(?:pdf|docx?)$")


def clean_source_name(raw: object) -> str:
    """The upload's file name without folders, 200 characters at most."""
    s = str(raw or "").replace("\\", "/").split("/")[-1].strip()
    s = "".join(ch for ch in s if ch.isprintable())
    return s[:200]


def file_article_key(name: object) -> str:
    """Shared key of a paper's files, or '' when the name carries no article id."""
    stem = _EXT.sub("", clean_source_name(name).lower())
    if not stem:
        return ""
    m = _NATURE.search(stem)
    if m:
        return f"n:{m.group(1)}-{int(m.group(2)) % 100:02d}-{m.group(3)}"
    cut = _PART_MARK.search(stem)
    if cut:
        stem = stem[: cut.start()]
    stem = stem.strip(" -_.")
    if len(stem) < 6 or sum(ch.isdigit() for ch in stem) < 4:
        return ""
    return "s:" + stem


def normalize_section(raw: object) -> str:
    v = str(raw or "").strip().lower()
    return v if v in PART_SECTIONS else "attached"


def part_section_for(entry: dict[str, Any] | None) -> str:
    from sentence_reading.cache.supplementary_library import (
        entry_doc_kind,
        entry_doc_role,
    )

    if entry_doc_role(entry) == "supplementary":
        return "supplementary"
    return "review" if entry_doc_kind(entry) == "review" else "attached"


def figure_prefix(section: str) -> str:
    return _FIG_PREFIX[normalize_section(section)]


def sentence_prefix(section: str) -> str:
    return _SENT_PREFIX[normalize_section(section)]


def normalize_parts(raw: object) -> list[dict[str, str]]:
    """``[{"id", "section"}]`` with empty and repeated ids dropped."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for row in raw:
        if isinstance(row, dict):
            pid = str(row.get("id") or "").strip()
            sec = normalize_section(row.get("section"))
        else:
            pid = str(row or "").strip()
            sec = "attached"
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({"id": pid, "section": sec})
    return out


def prior_parts(entry: dict[str, Any] | None) -> list[dict[str, str]]:
    """Parts already inside a merged paper; a design/152 merge reads as one SI."""
    if not isinstance(entry, dict):
        return []
    parts = normalize_parts(entry.get("merged_parts"))
    if parts:
        return parts
    sid = str(entry.get("merged_supplementary_id") or "").strip()
    if entry.get("supplementary_merged") and sid:
        return [{"id": sid, "section": "supplementary"}]
    return []


def merged_sections(entry: dict[str, Any] | None) -> list[str]:
    return [p["section"] for p in prior_parts(entry)]


def merged_tag(sections: list[str]) -> str:
    """'메인+서플먼터리' for the old one-SI merge, else '메인+보충+심사' and so on."""
    if not sections or all(s == "supplementary" for s in sections):
        return "메인+서플먼터리"
    names: list[str] = []
    for s in sections:
        t = _SECTION_TAGS.get(normalize_section(s))
        if t and t not in names:
            names.append(t)
    return "메인+" + "+".join(names)
