"""design/399 — a footer stamp inside a long PyMuPDF line no longer wipes the page."""

from __future__ import annotations

import inspect

from sentence_reading.api import app as app_mod
from sentence_reading.llm.debone_quality import (
    CHROME_LINE_MAX,
    drop_caption_text,
    practice_text_only,
    source_coverage_warnings,
    strip_back_matter,
)

_BODY = (
    "The precursors in the vapor phase are adsorbed on the carbon support during deposition. "
    "Thermal treatment then drives the two metals into one ordered lattice at high temperature. "
)
_STAMP = "7116 wileyonlinelibrary.com \u00a9 2016 WILEY-VCH Verlag GmbH & Co. KGaA, Weinheim. "


def test_stamp_inside_a_long_line_takes_only_its_sentence() -> None:
    line = _BODY * 6 + _STAMP + _BODY * 6
    assert len(line) > CHROME_LINE_MAX
    out = strip_back_matter(line)
    assert "wileyonlinelibrary" not in out and "WILEY-VCH" not in out
    assert out.count("ordered lattice") == 12
    assert len(out) > 0.9 * len(_BODY * 12)


def test_a_short_chrome_line_still_goes_whole() -> None:
    text = "Body sentence one is here and it is long enough.\nwww.nature.com/scientificreports 7\nNext."
    out = strip_back_matter(text)
    assert "nature.com" not in out and "scientificreports" not in out
    assert "Body sentence one" in out and "Next." in out


def test_a_paper_of_long_stamped_lines_keeps_its_prose() -> None:
    pages = [(_BODY * 8 + _STAMP + _BODY * 8) for _ in range(5)]
    raw = "\n".join(pages)
    assert len(practice_text_only(raw)) > 0.8 * len(raw)


def test_captions_leave_the_source_text_but_body_mentions_stay() -> None:
    caption = (
        "Figure 1. a) Schematic for the synthesis of bimetallic nanoparticles on a carbon "
        "black support. b) Composition control via deposition time analyzed with three methods."
    )
    body = "Figure 1 shows that the composition follows the deposition time closely in every run."
    text = f"{body} {caption} {_BODY}"
    out = drop_caption_text(text, [caption])
    assert "Schematic for the synthesis" not in out
    assert "Composition control via deposition" not in out
    assert body in out and "ordered lattice" in out
    assert drop_caption_text(text, []) == text


def test_source_text_ruler_names_a_lost_section() -> None:
    w = source_coverage_warnings(
        source_coverage=0.70, debone_coverage=0.85, denom_tokens=754, source_text_coverage=0.699
    )
    assert "source_text_coverage_low:0.70" in w
    ok = source_coverage_warnings(
        source_coverage=0.91, debone_coverage=0.85, denom_tokens=809, source_text_coverage=0.882
    )
    assert not any(x.startswith("source_text_coverage_low") for x in ok)
    small = source_coverage_warnings(
        source_coverage=1.0, debone_coverage=0.0, denom_tokens=23, source_text_coverage=0.1
    )
    assert small == ["coverage_denom_too_small:23"]


def test_split_handoff_measures_the_caption_free_source() -> None:
    src = inspect.getsource(app_mod)
    assert "drop_caption_text(\n                    text_pre_filter" in src
    assert "_src_tc, _src_missing = text_coverage(_src_text, sentences)" in src
    assert "source_text_coverage=_src_tc," in src
    assert '"source_text_coverage": round(float(_src_tc), 4),' in src
