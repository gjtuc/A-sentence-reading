"""
무엇을: PDF 페이지 텍스트 블록 → 2단(좌→우) reading order 재정렬.
왜: get_text 가 열을 가로로 섞을 때 문장 순서가 깨짐 (design/31).
한계: 깨끗한 2단 휴리스틱. 애매·3단+ 는 vision 강제 (vision_ocr).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MIN_BLOCKS = 4
_MIN_COL_BLOCKS = 2
# WHY: 좌우 군집 중심이 페이지 폭의 이만큼은 벌어져야 다단으로 봄
_MIN_CENTER_GAP_RATIO = 0.18


@dataclass(frozen=True)
class PageOrderResult:
    text: str
    is_multicolumn: bool
    reordered: bool


def _normalize_page_text(raw: str) -> str:
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw or "")
    raw = re.sub(r"(?<!\n)\n(?!\n)", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return raw.strip()


def _blocks_from_page(page: Any) -> list[tuple[float, float, float, float, str]]:
    out: list[tuple[float, float, float, float, str]] = []
    try:
        blocks = page.get_text("blocks") or []
    except Exception:
        return out
    for block in blocks:
        if len(block) < 5 or not isinstance(block[4], str):
            continue
        text = (block[4] or "").strip()
        if not text:
            continue
        # WHY: 너무 짧은 헤더/페이지번호만인 블록은 열 판별 노이즈
        if len(re.findall(r"[A-Za-z0-9]", text)) < 2:
            continue
        x0, y0, x1, y1 = float(block[0]), float(block[1]), float(block[2]), float(block[3])
        if x1 <= x0 or y1 <= y0:
            continue
        out.append((x0, y0, x1, y1, text))
    return out


def _join_blocks(blocks: list[tuple[float, float, float, float, str]]) -> str:
    # y 우선 · 같은 줄은 x
    ordered = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
    return _normalize_page_text("\n".join(b[4] for b in ordered))


def reorder_blocks_two_column(
    blocks: list[tuple[float, float, float, float, str]],
    *,
    page_width: float,
) -> PageOrderResult:
    """
    블록 리스트만으로 2단 재정렬 (테스트·추출 공용).
    page_width <= 0 이면 블록 bbox 로 추정.
    """
    if not blocks:
        return PageOrderResult(text="", is_multicolumn=False, reordered=False)

    if page_width <= 0:
        page_width = max(b[2] for b in blocks) - min(b[0] for b in blocks)
        if page_width <= 0:
            page_width = 1.0

    if len(blocks) < _MIN_BLOCKS:
        return PageOrderResult(
            text=_join_blocks(blocks),
            is_multicolumn=False,
            reordered=False,
        )

    centers = sorted((b[0] + b[2]) / 2.0 for b in blocks)
    mid = centers[len(centers) // 2]
    left = [b for b in blocks if (b[0] + b[2]) / 2.0 < mid]
    right = [b for b in blocks if (b[0] + b[2]) / 2.0 >= mid]

    if len(left) < _MIN_COL_BLOCKS or len(right) < _MIN_COL_BLOCKS:
        return PageOrderResult(
            text=_join_blocks(blocks),
            is_multicolumn=False,
            reordered=False,
        )

    left_c = sum((b[0] + b[2]) / 2.0 for b in left) / len(left)
    right_c = sum((b[0] + b[2]) / 2.0 for b in right) / len(right)
    gap = right_c - left_c
    if gap < page_width * _MIN_CENTER_GAP_RATIO:
        return PageOrderResult(
            text=_join_blocks(blocks),
            is_multicolumn=False,
            reordered=False,
        )

    # WHY: 열 안에서는 위에서 아래로 (좌 전체 → 우 전체)
    left_sorted = sorted(left, key=lambda b: (round(b[1], 1), b[0]))
    right_sorted = sorted(right, key=lambda b: (round(b[1], 1), b[0]))
    text = _normalize_page_text(
        "\n".join(b[4] for b in left_sorted)
        + "\n\n"
        + "\n".join(b[4] for b in right_sorted)
    )
    return PageOrderResult(text=text, is_multicolumn=True, reordered=True)


def order_page_text(page: Any) -> PageOrderResult:
    """fitz Page → 정규화 텍스트 + 다단 여부."""
    blocks = _blocks_from_page(page)
    try:
        width = float(page.rect.width)
    except Exception:
        width = 0.0
    if not blocks:
        try:
            raw = page.get_text("text") or ""
        except Exception:
            raw = ""
        return PageOrderResult(
            text=_normalize_page_text(raw),
            is_multicolumn=False,
            reordered=False,
        )
    return reorder_blocks_two_column(blocks, page_width=width)


def extract_text_by_page_ordered(pdf_path: Path) -> tuple[list[str], list[int]]:
    """
    페이지별 텍스트 + 다단으로 판정된 페이지 인덱스.
    암호 PDF → ValueError('encrypted_pdf') (extract 와 동일).
    """
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")
        pages: list[str] = []
        multi: list[int] = []
        for i, page in enumerate(doc):
            result = order_page_text(page)
            pages.append(result.text)
            if result.is_multicolumn:
                multi.append(i)
        return pages, multi
    finally:
        doc.close()


def detect_multicolumn_pages(pdf_path: Path) -> list[int]:
    """다단 페이지만 (텍스트 재추출 없이 플래그만 필요할 때)."""
    _, multi = extract_text_by_page_ordered(pdf_path)
    return multi


def merge_multicolumn_decision(
    decision: Any,
    multi_pages: list[int],
    page_count: int,
) -> Any:
    """
    QualityDecision 에 다단 페이지를 bad_pages 로 합친다.
    text_ok + 다단 있음 → repair_pages.
    """
    from sentence_reading.llm.extract_quality import QualityDecision

    if not isinstance(decision, QualityDecision):
        return decision
    multi = [i for i in multi_pages if 0 <= i < page_count]
    if not multi:
        return decision

    bad = list(decision.bad_pages)
    for i in multi:
        if i not in bad:
            bad.append(i)
    bad.sort()

    verdict = decision.verdict
    notes = decision.notes or ""
    tag = f"multicolumn:{len(multi)}"
    if tag not in notes:
        notes = f"{notes};{tag}".strip(";")

    if verdict == "text_ok":
        verdict = "repair_pages"
    elif verdict == "repair_pages" and not bad:
        verdict = "repair_pages"

    return QualityDecision(
        verdict=verdict,
        bad_pages=bad,
        notes=notes[:500],
        source=decision.source,
        warning=decision.warning,
    )
