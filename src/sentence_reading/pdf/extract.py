"""
무엇을: PDF 바이트 → 그림 목록 + 원문 텍스트.
왜: 학술 PDF의 Fig는 본문과 페이지가 어긋나므로, 그림을 별 리스트로 뽑아야
    상단 캐러셀에 올릴 수 있다.
다음에: PyMuPDF로 embedded image / 페이지 렌더 crop; 스캔본 OCR은 더 나중.
"""

from __future__ import annotations

from pathlib import Path

from sentence_reading.models import Figure


def extract_figures(pdf_path: Path) -> list[Figure]:
    """
    PDF에서 그림을 추출한다.

    # WHY: 스켈레톤에서는 의도적으로 막는다 — UI가 mock으로 먼저 검증되게.
    # NEXT: import fitz; page.get_images / get_pixmap; caption은 근처 텍스트 휴리스틱.
    # NOTE: compound figure (1a, 1b) 분리는 1차 범위 밖일 수 있음.
    """
    raise NotImplementedError(
        "PDF figure extraction is stubbed. Use mock session for UI. "
        f"Received path: {pdf_path}"
    )


def extract_text(pdf_path: Path) -> str:
    """
    PDF에서 읽기 순서에 가까운 원문 텍스트를 뽑는다.

    # NEXT: fitz page.get_text("text") 또는 blocks + reading order.
    # NOTE: 다단(two-column) 논문은 단순 get_text가 순서를 망가뜨릴 수 있다.
    """
    raise NotImplementedError(
        "PDF text extraction is stubbed. Use mock session for UI. "
        f"Received path: {pdf_path}"
    )
