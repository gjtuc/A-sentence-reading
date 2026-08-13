"""design/125 — caption-anchored Fig/Scheme/Table extract (0.3.49 · rich-v12)."""

from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.extract import extract_figures

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "src" / "sentence_reading" / "pdf" / "extract.py"
DESIGN = ROOT / "docs" / "design" / "125-caption-anchored-figures.md"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"


def _mini_png_bytes() -> bytes:
    """1×1 PNG via pixmap."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 60), 1)
    pix.clear_with(180)
    return pix.tobytes("png")


def _build_side_by_side_pdf(path: Path) -> None:
    """
    Page 1: two embeds + Fig. 1 / Fig. 2 captions (side-by-side — old image-first
    often kept only the left).
    Page 2: caption only (orphan / vector-like) Fig. 3.
    Page 3: caption above image Fig. 4.
    Also body sentence 'Figure 9 illustrates…' must NOT become a figure.
    """
    doc = fitz.open()
    png = _mini_png_bytes()

    # --- page 0: side-by-side ---
    page = doc.new_page(width=400, height=500)
    r1 = fitz.Rect(40, 80, 170, 200)
    r2 = fitz.Rect(220, 80, 350, 200)
    page.insert_image(r1, stream=png)
    page.insert_image(r2, stream=png)
    page.insert_text((40, 220), "Fig. 1. Left panel caption here.", fontsize=11)
    page.insert_text((220, 220), "Fig. 2. Right panel caption here.", fontsize=11)
    page.insert_text(
        (40, 400),
        "Figure 9 illustrates a body sentence that is not a caption.",
        fontsize=11,
    )

    # --- page 1: orphan caption (no embed) ---
    page = doc.new_page(width=400, height=500)
    # Drawing stands in for vector art above the caption.
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(60, 100, 340, 260))
    shape.finish(color=(0.2, 0.2, 0.6), fill=(0.85, 0.9, 1.0))
    shape.commit()
    page.insert_text((60, 290), "Fig. 3. Vector-like orphan caption.", fontsize=11)

    # --- page 2: caption above image ---
    page = doc.new_page(width=400, height=500)
    page.insert_text((60, 80), "Fig. 4. Caption sits above the artwork.", fontsize=11)
    page.insert_image(fitz.Rect(60, 110, 340, 280), stream=png)

    doc.save(path)
    doc.close()


def test_status_and_pipeline_pin() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.49"
    assert PIPELINE_VERSION == "rich-v12"
    assert "rich-v12" in TYPO.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    src = EXTRACT.read_text(encoding="utf-8")
    assert "design/125" in src
    assert "_labeled_caption_hits" in src
    assert "expand_compound" not in src.lower() or "never split" in src.lower()


def test_caption_anchored_recovers_side_by_side_and_orphan(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "caption_anchored.pdf"
    _build_side_by_side_pdf(pdf)
    figs = extract_figures(pdf)
    keys = [caption_key(f.caption) for f in figs]
    assert "fig:1" in keys
    assert "fig:2" in keys
    assert "fig:3" in keys
    assert "fig:4" in keys
    # Body "Figure 9 illustrates" must not mint a figure.
    assert "fig:9" not in keys
    assert all(f.image_src.startswith("data:image/png") for f in figs)


def test_real_cached_pdf_keeps_labeled_captions() -> None:
    """Regression on a stored paper: every punct-labeled caption should extract."""
    from sentence_reading.pdf.extract import (
        _FIG_CAPTION_LINE,
        _TABLE_CAPTION_LINE,
        _text_blocks,
    )

    srcs = list((ROOT / "data" / "cache" / "papers").glob("*/source.pdf"))
    if not srcs:
        return
    pdf = srcs[0]
    want: set[str] = set()
    doc = fitz.open(pdf)
    try:
        for page in doc:
            for *_box, text in _text_blocks(page):
                raw = (text or "").strip()
                if not raw:
                    continue
                for line in raw.split("\n"):
                    s = line.strip()
                    if _FIG_CAPTION_LINE.match(s) or _TABLE_CAPTION_LINE.match(s):
                        k = caption_key(_normalize_line(s))
                        if k:
                            want.add(k)
                        break
    finally:
        doc.close()
    if not want:
        return
    got = {caption_key(f.caption) for f in extract_figures(pdf)}
    missing = want - got
    assert not missing, f"missing caption keys {missing} from {pdf.parent.name}"


def _normalize_line(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", s).strip()
