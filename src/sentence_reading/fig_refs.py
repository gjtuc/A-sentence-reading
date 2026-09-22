"""
무엇을: 본문 Fig./Scheme/Table 참조 → 캐러셀 그림 인덱스 매칭.
왜: 문장 읽을 때 해당 그림으로 점프 힌트 (design/28). 강제 동기화 아님.
design/152 — slot_key fallback + bare S2 when supplementary merged.
design/164 — Figure 6C / 6(C) → base Figure 6 chip (panel suffix).
"""

from __future__ import annotations

import re
from typing import Any

# design/362 — two house styles name the same thing. ACS, RSC and Elsevier write
# `Figure S1`; Nature writes `Supplementary Fig. 1`. The word in front carries the
# same `S` the number would have carried, so read it. Measured over 88 papers, no
# main-paper caption prints any word in front of its number, so honouring this word
# cannot move a main figure into a supplementary slot.
_SUPP_WORD = r"(?:Supplementary|Supplemental|Supporting)"
_KIND_WORD = r"(?:Figures?|Figs?|Scheme|Table)"

# 본문·캡션 공통 — Fig. 2 / Figure S1 / Supplementary Fig. 1 / Scheme 1a / Table 3
# (?-i:[a-z]) — lowercase compound only; not Figure 6C panel (design/164).
_KIND_NUM = re.compile(
    rf"\b((?:{_SUPP_WORD}\s+)?{_KIND_WORD}\.?\s*(S?\d+(?-i:[a-z])?))\b",
    re.IGNORECASE,
)
# design/164 — Figure 6C / Figure 6(C) / Table 3B (panel within one figure)
_KIND_PANEL = re.compile(
    rf"\b((?:{_SUPP_WORD}\s+)?{_KIND_WORD}\.?\s*(S?\d+)\s*(?:\(([A-Za-z])\)|([A-Z])))\b",
    re.IGNORECASE,
)
# Re-parse of a matched token. Group 1 is the supplementary word when printed.
_TOKEN_NUM = re.compile(
    rf"(?:({_SUPP_WORD})\s+)?({_KIND_WORD})\.?\s*(S?\d+(?-i:[a-z])?)",
    re.IGNORECASE,
)
_TOKEN_PANEL = re.compile(
    rf"(?:({_SUPP_WORD})\s+)?({_KIND_WORD})\.?\s*(S?\d+)\s*(?:\(([A-Za-z])\)|([A-Z]))",
    re.IGNORECASE,
)
_BARE_S = re.compile(r"\b(S\d+[a-z]?)\b", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def strip_tags(html: str) -> str:
    return _TAG.sub(" ", html or "")


def _kind_token(kind_raw: str) -> str:
    k = (kind_raw or "").lower()
    if k.startswith("fig"):
        return "fig"
    if k.startswith("scheme"):
        return "scheme"
    return "table"


def _base_key_from_num(kind: str, num: str) -> str | None:
    num_lower = (num or "").lower()
    if num_lower.startswith("s"):
        m = re.match(r"^s(\d+)", num_lower)
        if not m:
            return None
        return f"{kind}:s{int(m.group(1))}"
    m = re.match(r"^(\d+)", num_lower)
    if not m:
        return None
    return f"{kind}:{int(m.group(1))}"


def _base_display_label(kind_raw: str, num: str) -> str:
    k = (kind_raw or "").strip()
    if k.lower().startswith("fig"):
        return f"Figure {num}"
    if k.lower().startswith("scheme"):
        return f"Scheme {num}"
    return f"Table {num}"


def _supp_num(supp_word: str | None, num: str) -> str:
    """`S` the number, when the label printed the word `Supplementary` (design/362)."""
    n = (num or "").lower()
    if supp_word and not n.startswith("s"):
        return f"s{n}"
    return n


def _norm_key(raw: str) -> str | None:
    m = _KIND_NUM.search(raw or "")
    if not m:
        return None
    parts = _TOKEN_NUM.match(m.group(1))
    if not parts:
        return None
    kind = _kind_token(parts.group(2))
    num = _supp_num(parts.group(1), parts.group(3))
    return f"{kind}:{num}"


def _panel_parse(m: re.Match[str]) -> tuple[str, str] | None:
    """Return (base_display_label, base_key) for a panel ref match."""
    full = m.group(1)
    inner = _TOKEN_PANEL.match(full)
    if not inner:
        return None
    paren = inner.group(4)
    upper = inner.group(5)
    if upper and not upper.isupper():
        return None
    kind_raw = inner.group(2)
    num = _supp_num(inner.group(1), inner.group(3)).upper()
    kind = _kind_token(kind_raw)
    base_key = _base_key_from_num(kind, num)
    if not base_key:
        return None
    return (_base_display_label(kind_raw, num), base_key)


def _want_key(ref_label: str, *, supplementary_merged: bool = False) -> str | None:
    want = _norm_key(ref_label)
    if want:
        return want
    if supplementary_merged:
        m = _BARE_S.fullmatch((ref_label or "").strip())
        if m:
            return f"fig:{m.group(1).lower()}"
    return None


def _panel_label_and_key(raw: str) -> tuple[str, str] | None:
    m = _KIND_PANEL.search(raw or "")
    if not m:
        return None
    parsed = _panel_parse(m)
    return parsed


def _match_keys_for_label(
    ref_label: str, *, supplementary_merged: bool = False
) -> list[str]:
    """Keys to try in order: exact then base (design/164)."""
    keys: list[str] = []
    panel = _panel_label_and_key(ref_label)
    if panel:
        _, base_key = panel
        keys.append(base_key)
    exact = _want_key(ref_label, supplementary_merged=supplementary_merged)
    if exact and exact not in keys:
        keys.append(exact)
        parts = exact.split(":", 1)
        if len(parts) == 2:
            base = _base_key_from_num(parts[0], parts[1])
            if base and base != exact and base not in keys:
                keys.append(base)
    return keys


def parse_refs(text: str, *, supplementary_merged: bool = False) -> list[str]:
    """본문에서 참조 표시 문자열 목록 (등장 순 · base_key 중복 제거)."""
    plain = strip_tags(text)
    hits: list[tuple[int, str, str]] = []
    for m in _KIND_NUM.finditer(plain):
        label = re.sub(r"\s+", " ", m.group(1).strip())
        key = _want_key(label, supplementary_merged=supplementary_merged)
        if not key:
            continue
        hits.append((m.start(), label, key))
    for m in _KIND_PANEL.finditer(plain):
        parsed = _panel_parse(m)
        if not parsed:
            continue
        label, key = parsed
        hits.append((m.start(), label, key))
    hits.sort(key=lambda t: t[0])
    out: list[str] = []
    seen: set[str] = set()
    for _, label, key in hits:
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    if supplementary_merged:
        for m in _BARE_S.finditer(plain):
            label = m.group(1)
            key = _want_key(label, supplementary_merged=True)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(label)
    return out


def caption_key(caption: str) -> str | None:
    """캡션 선두 번호 키. 실패 시 None."""
    head = strip_tags(caption).strip()
    if not head:
        return None
    m = _KIND_NUM.match(head) or _KIND_NUM.search(head[:80])
    if not m:
        return None
    return _norm_key(m.group(1))


def _figure_slot_key(fig: Any) -> str:
    sk = getattr(fig, "slot_key", None)
    if sk is None and isinstance(fig, dict):
        sk = fig.get("slot_key") or ""
    return str(sk or "").strip().lower()


def _slot_wants(want: str) -> list[str]:
    if want.startswith("scheme:"):
        return [want, want.replace("scheme:", "fig:", 1)]
    return [want]


def _figure_caption_key(fig: Any) -> str | None:
    cap = getattr(fig, "caption", None)
    if cap is None and isinstance(fig, dict):
        cap = fig.get("caption") or ""
    return caption_key(str(cap or ""))


def _index_for_key(figures: list[Any], want: str) -> int | None:
    # design/362 — `Scheme 1` now has its own slot. Papers ingested before that
    # stored their schemes under `fig:N`, so fall back to that key — but only after
    # no slot answers to `scheme:1`, or a paper holding both would hand `Scheme 1`
    # the picture that belongs to `Figure 1`.
    for slot_want in _slot_wants(want):
        for i, fig in enumerate(figures or []):
            if _figure_slot_key(fig) == slot_want:
                return i
    for i, fig in enumerate(figures or []):
        key = _figure_caption_key(fig)
        if not key:
            continue
        if key == want:
            return i
        base = _base_key_from_num(*key.split(":", 1))
        if base and base == want:
            return i
    return None


def match_figure_index(
    figures: list[Any],
    ref_label: str,
    *,
    supplementary_merged: bool = False,
) -> int | None:
    """figures[i] caption/slot_key 와 ref 매칭. 없으면 None."""
    for want in _match_keys_for_label(
        ref_label, supplementary_merged=supplementary_merged
    ):
        idx = _index_for_key(figures, want)
        if idx is not None:
            return idx
    return None


def hints_for_sentence(
    text: str,
    figures: list[Any],
    *,
    supplementary_merged: bool = False,
) -> list[dict[str, Any]]:
    """[{ref, figure_index}, ...] — 매칭된 것만; figure_index 중복 제거."""
    rows: list[dict[str, Any]] = []
    seen_idx: set[int] = set()
    for label in parse_refs(text, supplementary_merged=supplementary_merged):
        idx = match_figure_index(
            figures, label, supplementary_merged=supplementary_merged
        )
        if idx is None or idx in seen_idx:
            continue
        seen_idx.add(idx)
        rows.append({"ref": label, "figure_index": idx})
    return rows


def first_fig_table_chip_sentence_index(
    sentences: list[Any],
    figures: list[Any],
    *,
    supplementary_merged: bool = False,
) -> int | None:
    """design/183 — first global sentence index with a *matched* Fig/Table chip.

    Same predicate as mobile ``hintsForSentence`` / UI chips. Unmatched refs
    and bibliography cite numbers do not count. ``None`` if no chip exists.
    """
    for i, s in enumerate(sentences or []):
        if isinstance(s, dict):
            text = str(s.get("text") or "")
        else:
            text = str(getattr(s, "text", "") or "")
        if not strip_tags(text).strip():
            continue
        if hints_for_sentence(
            text,
            figures,
            supplementary_merged=supplementary_merged,
        ):
            return i
    return None
