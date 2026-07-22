"""
무엇을: PDF 페이지 PNG → Gemini vision → plain text, 품질 라우터와 병합.
왜: 스캔·손상 페이지는 get_text가 비거나 순서가 틀리므로 이미지가 필요하다.
다음에: 페이지 묶음(batch) vision, DPI 자동 조절.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sentence_reading.llm.env import gemini_api_key, gemini_model
from sentence_reading.llm.extract_quality import (
    QualityDecision,
    decide_extract_quality,
)
from sentence_reading.pdf.extract import join_page_texts, render_page_png

_VISION_PAGE_CAP = 40

_OCR_SYSTEM = """You read one academic PDF page image and return its body text.
Restore reading order (two-column: left column top-to-bottom, then right).
Output plain text only — no HTML, no markdown fences, no commentary.
Skip pure decorative headers/footers if they repeat; keep real section titles and prose.
Do not invent chemistry or claims that are not visible on the page.
If the page is blank or unreadable, return an empty string.
"""


@dataclass
class RecoverResult:
    text: str
    pages: list[str]
    warnings: list[str] = field(default_factory=list)
    vision_pages: list[int] = field(default_factory=list)
    decision: QualityDecision | None = None


def _call_gemini_vision(system: str, user_text: str, png: bytes) -> str:
    from google import genai
    from google.genai import types

    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")

    client = genai.Client(api_key=key)
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_text),
                types.Part.from_bytes(data=png, mime_type="image/png"),
            ],
        )
    ]
    response = client.models.generate_content(
        model=gemini_model(),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            t = getattr(part, "text", None) or ""
            if t:
                parts.append(t)
    # WHY: 빈 페이지는 빈 문자열이 정상 — 예외로 치지 않음
    return "".join(parts).strip()


def ocr_page_png(png: bytes, *, page_index: int, page_count: int) -> str:
    user = (
        f"Transcribe page {page_index + 1} of {page_count} "
        f"(0-based index {page_index}). Plain text only."
    )
    return _call_gemini_vision(_OCR_SYSTEM, user, png)


def _select_vision_pages(
    decision: QualityDecision, page_count: int
) -> list[int]:
    if decision.verdict == "text_ok":
        return []
    if decision.verdict == "full_vision":
        indices = list(range(page_count))
    else:
        indices = [i for i in decision.bad_pages if 0 <= i < page_count]
    if len(indices) > _VISION_PAGE_CAP:
        # WHY: bad_pages 우선, 나머지는 앞쪽
        preferred = [i for i in indices if i in set(decision.bad_pages)]
        rest = [i for i in indices if i not in set(preferred)]
        indices = (preferred + rest)[:_VISION_PAGE_CAP]
    return indices


def recover_pdf_text(
    pdf_path: Path,
    pages: list[str],
    *,
    on_progress: Callable[[str, int, int, str], None] | None = None,
) -> RecoverResult:
    """
    품질 판정 후 필요 시 vision OCR로 페이지 텍스트를 교체한다.
    on_progress(stage, done, total, message)
    """
    warnings: list[str] = []
    working = list(pages)
    n = len(working)

    if on_progress:
        on_progress("quality", 0, 1, "추출 품질 보는 중")

    if not gemini_api_key():
        if on_progress:
            on_progress("quality", 1, 1, "키 없음 — 텍스트만")
        return RecoverResult(
            text=join_page_texts(working),
            pages=working,
            warnings=["gemini_key_missing"],
            decision=QualityDecision(
                verdict="text_ok",
                source="fallback",
                warning="gemini_key_missing",
            ),
        )

    decision = decide_extract_quality(working)
    if decision.warning:
        warnings.append(decision.warning)

    if on_progress:
        on_progress("quality", 1, 1, decision.notes or decision.verdict)

    vision_indices = _select_vision_pages(decision, n)
    if not vision_indices:
        return RecoverResult(
            text=join_page_texts(working),
            pages=working,
            warnings=warnings,
            decision=decision,
        )

    if len(decision.bad_pages) > _VISION_PAGE_CAP or (
        decision.verdict == "full_vision" and n > _VISION_PAGE_CAP
    ):
        warnings.append("vision_page_cap")

    total = len(vision_indices)
    failed = 0
    for k, page_index in enumerate(vision_indices):
        if on_progress:
            on_progress(
                "vision",
                k,
                total,
                f"페이지 이미지 읽는 중 {k + 1}/{total}",
            )
        try:
            png = render_page_png(pdf_path, page_index)
            text = ocr_page_png(png, page_index=page_index, page_count=n)
            working[page_index] = (text or "").strip()
        except Exception:  # noqa: BLE001
            failed += 1

    if on_progress:
        on_progress("vision", total, total, "이미지 읽기 끝")

    if failed:
        warnings.append(f"vision_failed:{failed}/{total}")
    if failed == total:
        warnings.append("vision_failed")
        # WHY: 전부 실패면 원본 PyMuPDF 텍스트 유지
        return RecoverResult(
            text=join_page_texts(pages),
            pages=list(pages),
            warnings=warnings,
            vision_pages=[],
            decision=decision,
        )

    warnings.append("vision_ocr_used")
    warnings.append(
        "vision_pages:" + ",".join(str(i) for i in vision_indices)
    )
    return RecoverResult(
        text=join_page_texts(working),
        pages=working,
        warnings=warnings,
        vision_pages=vision_indices,
        decision=decision,
    )
