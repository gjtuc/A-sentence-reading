"""
무엇을: 본문 Fig./Scheme/Table 참조 → 캐러셀 그림 인덱스 매칭.
왜: 문장 읽을 때 해당 그림으로 점프 힌트 (design/28). 강제 동기화 아님.
design/152 — slot_key fallback + bare S2 when supplementary merged.
"""

from __future__ import annotations

import re
from typing import Any

# 본문·캡션 공통 — Fig. 2 / Figure S1 / Scheme 1a / Table 3
_KIND_NUM = re.compile(
    r"\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?))\b",
    re.IGNORECASE,
)
_BARE_S = re.compile(r"\b(S\d+[a-z]?)\b", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def strip_tags(html: str) -> str:
    return _TAG.sub(" ", html or "")


def _norm_key(raw: str) -> str | None:
    m = _KIND_NUM.search(raw or "")
    if not m:
        return None
    token = m.group(1)
    parts = re.match(
        r"(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?)",
        token,
        re.IGNORECASE,
    )
    if not parts:
        return None
    kind_raw = parts.group(1).lower()
    num = parts.group(2).lower()
    if kind_raw.startswith("fig"):
        kind = "fig"
    elif kind_raw.startswith("scheme"):
        kind = "scheme"
    else:
        kind = "table"
    return f"{kind}:{num}"


def _want_key(ref_label: str, *, supplementary_merged: bool = False) -> str | None:
    want = _norm_key(ref_label)
    if want:
        return want
    if supplementary_merged:
        m = _BARE_S.fullmatch((ref_label or "").strip())
        if m:
            return f"fig:{m.group(1).lower()}"
    return None


def parse_refs(text: str, *, supplementary_merged: bool = False) -> list[str]:
    """본문에서 참조 표시 문자열 목록 (등장 순 · 중복 제거)."""
    plain = strip_tags(text)
    out: list[str] = []
    seen: set[str] = set()
    for m in _KIND_NUM.finditer(plain):
        label = re.sub(r"\s+", " ", m.group(1).strip())
        key = _want_key(label, supplementary_merged=supplementary_merged)
        if not key or key in seen:
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


def match_figure_index(
    figures: list[Any],
    ref_label: str,
    *,
    supplementary_merged: bool = False,
) -> int | None:
    """figures[i] caption/slot_key 와 ref 매칭. 없으면 None."""
    want = _want_key(ref_label, supplementary_merged=supplementary_merged)
    if not want:
        return None
    want_slot = want.replace("scheme:", "fig:")
    for i, fig in enumerate(figures or []):
        sk = _figure_slot_key(fig)
        if sk and sk == want_slot:
            return i
        cap = getattr(fig, "caption", None)
        if cap is None and isinstance(fig, dict):
            cap = fig.get("caption") or ""
        key = caption_key(str(cap or ""))
        if key == want:
            return i
    return None


def hints_for_sentence(
    text: str,
    figures: list[Any],
    *,
    supplementary_merged: bool = False,
) -> list[dict[str, Any]]:
    """[{ref, figure_index}, ...] — 매칭된 것만."""
    rows: list[dict[str, Any]] = []
    for label in parse_refs(text, supplementary_merged=supplementary_merged):
        idx = match_figure_index(
            figures, label, supplementary_merged=supplementary_merged
        )
        if idx is None:
            continue
        rows.append({"ref": label, "figure_index": idx})
    return rows
