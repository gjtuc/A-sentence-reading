"""design/323 — ink-based clipping probe. Synthetic images only."""

from __future__ import annotations

import io
from pathlib import Path

from sentence_reading.pdf.clip_probe import (
    ClipReport,
    clip_report,
    clip_verdicts,
)

ROOT = Path(__file__).resolve().parents[1]


def _png(draw_fn, size=(200, 200)) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", size, (255, 255, 255))
    draw_fn(ImageDraw.Draw(im), size)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_blank_crop_is_named():
    png = _png(lambda d, s: None)
    rep = clip_report(png)
    assert rep is not None
    assert rep.blank is True
    assert rep.touches == ()


def test_figure_with_margins_touches_no_edge():
    png = _png(lambda d, s: d.rectangle([40, 40, 160, 160], fill=(10, 10, 10)))
    rep = clip_report(png)
    assert rep is not None
    assert rep.blank is False
    assert rep.touches == ()
    assert rep.ink_frac > 0.3


def test_ink_running_off_the_right_edge_is_flagged():
    png = _png(lambda d, s: d.rectangle([40, 40, s[0], 160], fill=(10, 10, 10)))
    rep = clip_report(png)
    assert rep is not None
    assert "right" in rep.touches
    assert "left" not in rep.touches


def test_ink_off_two_edges_reads_as_cut():
    png = _png(lambda d, s: d.rectangle([0, 40, s[0], 160], fill=(10, 10, 10)))
    rep = clip_report(png)
    assert rep is not None
    assert {"left", "right"} <= set(rep.touches)
    assert clip_verdicts([("fig:1", rep)]) == ["figure_crop_edge_ink:1"]


def test_a_tiny_speck_at_the_edge_is_not_a_cut():
    # A stray pixel run under the minimum fraction must not cry clipping.
    png = _png(lambda d, s: d.rectangle([0, 98, 3, 101], fill=(10, 10, 10)))
    rep = clip_report(png)
    assert rep is not None
    assert rep.touches == ()


def test_near_white_counts_as_background():
    png = _png(lambda d, s: d.rectangle([0, 0, s[0], s[1]], fill=(250, 250, 250)))
    rep = clip_report(png)
    assert rep is not None
    assert rep.blank is True


def test_unreadable_bytes_report_none_not_a_guess():
    assert clip_report(b"") is None
    assert clip_report(b"not a png") is None


def test_verdicts_separate_blank_cut_and_unreadable():
    blank = clip_report(_png(lambda d, s: None))
    cut = clip_report(
        _png(lambda d, s: d.rectangle([0, 40, s[0], 160], fill=(10, 10, 10)))
    )
    out = clip_verdicts([("a", blank), ("b", cut), ("c", None)])
    assert "figure_crop_blank:1" in out
    assert "figure_crop_edge_ink:1" in out
    assert "figure_crop_unreadable:1" in out


def test_report_dict_is_json_safe_and_has_no_paper_text():
    rep = clip_report(_png(lambda d, s: d.rectangle([40, 40, 160, 160], fill=(0, 0, 0))))
    assert isinstance(rep, ClipReport)
    d = rep.to_dict()
    import json

    json.dumps(d, ensure_ascii=True)
    assert set(d) == {
        "width",
        "height",
        "ink_box",
        "touches",
        "touch_n",
        "ink_frac",
        "blank",
    }


def test_harness_exists_and_keeps_paper_text_off_the_console():
    h = ROOT / "scripts/extract_audit.py"
    assert h.is_file()
    src = h.read_text(encoding="utf-8")
    assert "ensure_ascii=True" in src
    # Must be able to run without spending Gemini tokens.
    assert "--with-gemini" in src
    assert "split_into_sentences_detailed" in src
