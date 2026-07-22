"""
무엇을: PyMuPDF 추출 텍스트 품질 판정 (규칙 + Gemini 품질맵).
왜: 스캔·다단 손상을 “오타율”이 아니라 복구 경로(vision 여부)로 라우팅한다.
다음에: 블록 좌표 기반 다단 힌트.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sentence_reading.llm.env import gemini_api_key

_QUALITY_MAX_CHARS = 80_000
_EMPTY_PAGE_ALNUM = 15
_SPARSE_TOTAL_ALNUM = 50
_EMPTY_PAGE_RATIO = 0.45

_QUALITY_SYSTEM = """You judge academic PDF text extraction quality (PyMuPDF get_text).
You do NOT count typos. Decide whether page images (vision OCR) are needed.

Flag problems such as:
- Almost no real prose (likely scanned / image-only pages)
- Gibberish, severed words, missing large sections
- Fluent English but suspicious reading order (two-column mix-ups)

Be conservative: if unsure, prefer text_ok to avoid expensive vision.
Output JSON only, no markdown fences.
"""

_QUALITY_USER = """Judge this page-annotated extraction. Pages are 0-based.

Return JSON:
{{
  "verdict": "text_ok" | "repair_pages" | "full_vision",
  "bad_pages": [0, 3],
  "notes": "short reason"
}}

Rules:
- text_ok: extracted text is usable for a sentence reader (ignore normal PDF quirks like flattened subscripts).
- repair_pages: only listed bad_pages need vision; bad_pages must be valid 0-based indices that appear in the sample.
- full_vision: most/all pages need vision (scan or severe damage).
- Prefer text_ok when uncertain.

EXTRACTED PAGES:
---
{sample}
---
"""


@dataclass
class QualityDecision:
    """규칙 또는 Gemini 품질맵 결과."""

    verdict: str  # text_ok | repair_pages | full_vision
    bad_pages: list[int] = field(default_factory=list)
    notes: str = ""
    source: str = "heuristic"  # heuristic | gemini | fallback
    warning: str | None = None


def total_alnum(pages: list[str]) -> int:
    return sum(len(re.findall(r"[A-Za-z0-9]", p or "")) for p in pages)


def _page_alnum(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]", text or ""))


def heuristic_gate(pages: list[str]) -> QualityDecision | None:
    """
    값싼 1차. None이면 Gemini 품질맵으로 넘긴다.
    clear scan → full_vision; 그 외 대부분은 None (품질맵).
    """
    n = len(pages)
    if n == 0:
        return QualityDecision(
            verdict="full_vision",
            notes="no_pages",
            source="heuristic",
        )

    alnum = total_alnum(pages)
    if alnum < _SPARSE_TOTAL_ALNUM:
        return QualityDecision(
            verdict="full_vision",
            notes=f"sparse_alnum:{alnum}",
            source="heuristic",
        )

    empty = sum(1 for p in pages if _page_alnum(p) < _EMPTY_PAGE_ALNUM)
    if n >= 2 and (empty / n) >= _EMPTY_PAGE_RATIO:
        return QualityDecision(
            verdict="full_vision",
            notes=f"empty_page_ratio:{empty}/{n}",
            source="heuristic",
        )

    # WHY: 과잉 vision 방지 — 애매하면 Gemini에게 맡김
    return None


def _build_page_sample(pages: list[str], max_chars: int = _QUALITY_MAX_CHARS) -> str:
    blocks: list[str] = []
    for i, text in enumerate(pages):
        body = (text or "").strip() or "(empty)"
        blocks.append(f"--- PAGE {i} ---\n{body}")
    joined = "\n\n".join(blocks)
    if len(joined) <= max_chars:
        return joined
    # head + tail pages 우선
    head_budget = max_chars * 4 // 5
    out: list[str] = []
    size = 0
    for block in blocks:
        if size + len(block) + 2 > head_budget:
            break
        out.append(block)
        size += len(block) + 2
    tail: list[str] = []
    tsize = 0
    tail_budget = max_chars - size - 40
    for block in reversed(blocks):
        if block in out:
            break
        if tsize + len(block) + 2 > tail_budget:
            break
        tail.append(block)
        tsize += len(block) + 2
    tail.reverse()
    mid = "\n\n[...middle pages omitted...]\n\n" if tail else ""
    return "\n\n".join(out) + mid + "\n\n".join(tail)


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        return json.loads(m.group(0))


def _parse_quality(payload: dict, page_count: int) -> QualityDecision:
    if not isinstance(payload, dict):
        return QualityDecision(
            verdict="text_ok",
            source="fallback",
            warning="quality_map_bad_json",
            notes="bad_json",
        )
    raw_verdict = str(payload.get("verdict") or "text_ok").strip().lower()
    if raw_verdict not in ("text_ok", "repair_pages", "full_vision"):
        raw_verdict = "text_ok"
    bad: list[int] = []
    rows = payload.get("bad_pages")
    if isinstance(rows, list):
        for x in rows:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= i < page_count and i not in bad:
                bad.append(i)
    notes = str(payload.get("notes") or "").strip()[:500]
    if raw_verdict == "repair_pages" and not bad:
        # WHY: 페이지 없으면 과잉 full_vision 대신 text_ok
        raw_verdict = "text_ok"
    return QualityDecision(
        verdict=raw_verdict,
        bad_pages=bad,
        notes=notes,
        source="gemini",
    )


def gemini_quality_map(pages: list[str]) -> QualityDecision:
    """텍스트만으로 품질맵. 실패 시 text_ok + warning."""
    if not gemini_api_key():
        return QualityDecision(
            verdict="text_ok",
            source="fallback",
            warning="gemini_key_missing",
            notes="no_key",
        )
    # 순환 import 방지: debone의 _call_gemini 재사용
    from sentence_reading.llm.debone import _call_gemini

    sample = _build_page_sample(pages)
    try:
        raw = _call_gemini(
            _QUALITY_SYSTEM,
            _QUALITY_USER.format(sample=sample),
        )
        payload = _extract_json(raw)
        return _parse_quality(payload, len(pages))
    except Exception as exc:  # noqa: BLE001
        return QualityDecision(
            verdict="text_ok",
            source="fallback",
            warning=f"quality_map_failed:{exc}",
            notes="quality_map_failed",
        )


def decide_extract_quality(pages: list[str]) -> QualityDecision:
    """규칙 게이트 → 필요 시 Gemini 품질맵."""
    gated = heuristic_gate(pages)
    if gated is not None:
        return gated
    return gemini_quality_map(pages)
