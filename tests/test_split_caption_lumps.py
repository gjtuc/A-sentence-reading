"""design/137 — split caption lumps; fail-closed (0.3.71 · rich-v18)."""

from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.caption_lumps import (
    CaptionLumpError,
    count_inline_labels,
    distinct_caption_keys_in_text,
    maybe_fail_ambiguous_line,
    split_caption_lumps_enabled,
    split_line_caption_segments,
    validate_extracted_figures,
)
from sentence_reading.pdf.extract import _is_caption_line, extract_figures
from sentence_reading.models import Figure

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "137-split-caption-lumps.md"
PUB = ROOT / "mobile" / "pubspec.yaml"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"
EXTRACT = ROOT / "src" / "sentence_reading" / "pdf" / "extract.py"


def _mini_png() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 90), 1)
    pix.clear_with(200)
    return pix.tobytes("png")


def _build_lumped_two_figs(path: Path) -> None:
    """Two Fig captions on one line under two images — must split to fig:1 and fig:2."""
    doc = fitz.open()
    png = _mini_png()
    page = doc.new_page(width=440, height=700)
    # WHY: library save needs normalize_title_key >= 24 (design/108); short adb filenames fail E2E.
    page.insert_text(
        (40, 30),
        "Synthetic Paper Alpha: Nickel Catalysts for DRM — Lumped Fig Captions",
        fontsize=12,
    )
    page.insert_text((40, 52), "Ada Alpha, Ben Beta", fontsize=10)
    page.insert_text((40, 72), "Abstract", fontsize=11)
    page.insert_text(
        (40, 92),
        "Nickel catalysts on alumina supports show activity in dry reforming. "
        "We compare alpha and beta morphologies under identical conditions.",
        fontsize=10,
    )
    page.insert_text(
        (40, 130),
        "1. Introduction. Body text continues so ingest can finish and save to the library.",
        fontsize=10,
    )
    page.insert_image(fitz.Rect(40, 160, 200, 280), stream=png)
    page.insert_image(fitz.Rect(240, 160, 400, 280), stream=png)
    page.insert_text(
        (40, 300),
        "Fig. 1. Alpha catalyst overview. Fig. 2. Beta support morphology.",
        fontsize=10,
    )
    page.insert_text(
        (40, 330),
        "2. Results. Both samples were characterized by XRD and TEM. "
        "The alpha sample showed higher surface area than the beta sample.",
        fontsize=10,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()


def _build_ambiguous_lump(path: Path) -> None:
    """Two labels but second chunk is not a valid caption → fail-closed."""
    doc = fitz.open()
    png = _mini_png()
    page = doc.new_page(width=420, height=400)
    page.insert_image(fitz.Rect(40, 40, 360, 160), stream=png)
    page.insert_text(
        (40, 190),
        "Fig. 1. Valid caption title. Fig. 2",
        fontsize=10,
    )
    doc.save(path)
    doc.close()


def test_status_and_docs_pin_split_caption_lumps():
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.71"
    assert st["pipeline_version"] == "rich-v18"
    assert st["split_caption_lumps"] is True
    assert st["mobile_split_caption_lumps"] is True
    assert PIPELINE_VERSION == "rich-v18"
    assert "rich-v18" in TYPO.read_text(encoding="utf-8")
    assert "0.3.71" in PUB.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    assert "ASR_SPLIT_CAPTION_LUMPS" in DESIGN.read_text(encoding="utf-8")
    assert "design/137" in EXTRACT.read_text(encoding="utf-8")


def test_split_line_segments_two_figs():
    line = "Fig. 1. First title. Fig. 2. Second title."
    segs = split_line_caption_segments(line)
    assert len(segs) == 2
    assert segs[0].startswith("Fig. 1")
    assert segs[1].startswith("Fig. 2")
    keys = distinct_caption_keys_in_text(line)
    assert keys == ["fig:1", "fig:2"]
    assert count_inline_labels(line) == 2


def test_extract_splits_lumped_line(tmp_path: Path):
    pdf = tmp_path / "lump.pdf"
    _build_lumped_two_figs(pdf)
    figs = extract_figures(pdf)
    keys = sorted(caption_key(f.caption) for f in figs if caption_key(f.caption))
    assert "fig:1" in keys
    assert "fig:2" in keys
    for f in figs:
        assert len(distinct_caption_keys_in_text(f.caption)) <= 1


def test_ambiguous_lump_fail_closed(tmp_path: Path):
    pdf = tmp_path / "bad.pdf"
    _build_ambiguous_lump(pdf)
    try:
        extract_figures(pdf)
        raise AssertionError("expected CaptionLumpError")
    except CaptionLumpError as exc:
        assert "구분" in str(exc) or "덩어리" in str(exc)


def test_validate_extracted_figures_rejects_multi_key():
    lump = Figure(
        id="fig-0001",
        image_src="data:image/png;base64,AA==",
        caption="Fig. 1. A. Fig. 2. B.",
        page_index=0,
    )
    try:
        validate_extracted_figures([lump])
        raise AssertionError("expected CaptionLumpError")
    except CaptionLumpError:
        pass


def test_kill_switch_skips_validate(monkeypatch):
    monkeypatch.setenv("ASR_SPLIT_CAPTION_LUMPS", "0")
    assert split_caption_lumps_enabled() is False
    lump = Figure(
        id="fig-0001",
        image_src="data:image/png;base64,AA==",
        caption="Fig. 1. A. Fig. 2. B.",
        page_index=0,
    )
    validate_extracted_figures([lump])  # no raise when disabled


def test_body_reference_not_counted_as_second_label():
    line = "Figure 4 illustrates conversion over time."
    assert count_inline_labels(line) == 1
    segs = split_line_caption_segments(line)
    assert len(segs) == 1


def test_maybe_fail_ambiguous_line_raises():
    line = "Fig. 1. OK. Fig. 2"
    segs = split_line_caption_segments(line)
    valid = [(i, s) for i, s in enumerate(segs) if _is_caption_line(s, fig_scheme=True, table=False)]
    try:
        maybe_fail_ambiguous_line(
            line,
            valid,
            is_caption_line=lambda s: _is_caption_line(s, fig_scheme=True, table=False),
        )
        raise AssertionError("expected CaptionLumpError")
    except CaptionLumpError:
        pass


def test_null_byte_in_line_does_not_crash():
    line = "Fig.\x001. Title"
    segs = split_line_caption_segments(line)
    assert segs
