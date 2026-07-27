"""
무엇을: 본문 Fig./Scheme/Table 참조 → 캐러셀 그림 인덱스 매칭.
왜: 문장 읽을 때 해당 그림으로 점프 힌트 (design/28). 강제 동기화 아님.
"""

from __future__ import annotations

import re
from typing import Any

# 본문·캡션 공통 — Fig. 2 / Figure S1 / Scheme 1a / Table 3
_KIND_NUM = re.compile(
    r"\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?))\b",
    re.IGNORECASE,
)
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


def parse_refs(text: str) -> list[str]:
    """본문에서 참조 표시 문자열 목록 (등장 순 · 중복 제거)."""
    plain = strip_tags(text)
    out: list[str] = []
    seen: set[str] = set()
    for m in _KIND_NUM.finditer(plain):
        label = re.sub(r"\s+", " ", m.group(1).strip())
        key = _norm_key(label)
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
    # 캡션은 보통 맨 앞이 Fig.…
    m = _KIND_NUM.match(head) or _KIND_NUM.search(head[:80])
    if not m:
        return None
    return _norm_key(m.group(1))


def match_figure_index(figures: list[Any], ref_label: str) -> int | None:
    """figures[i].caption 과 ref 매칭. 없으면 None."""
    want = _norm_key(ref_label)
    if not want:
        return None
    for i, fig in enumerate(figures or []):
        cap = getattr(fig, "caption", None)
        if cap is None and isinstance(fig, dict):
            cap = fig.get("caption") or ""
        key = caption_key(str(cap or ""))
        if key == want:
            return i
    return None


def hints_for_sentence(text: str, figures: list[Any]) -> list[dict[str, Any]]:
    """[{ref, figure_index}, ...] — 매칭된 것만."""
    rows: list[dict[str, Any]] = []
    for label in parse_refs(text):
        idx = match_figure_index(figures, label)
        if idx is None:
            continue
        rows.append({"ref": label, "figure_index": idx})
    return rows
