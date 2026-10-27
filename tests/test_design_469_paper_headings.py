# -*- coding: utf-8 -*-
"""design/469 — the paper's own headings, kept once per paper."""

from __future__ import annotations

from sentence_reading.cache import paper_cache as pc
from sentence_reading.models import PaperSession, Sentence
from sentence_reading.paper_headings import clean_headings, heading_anchors
from sentence_reading.pdf.section_flow import FlowBox, heading_text, order_boxes

_PAGES = [{"width": 595.0, "height": 792.0}, {"width": 595.0, "height": 792.0}]

_S = [
    "The structure of bimetallic catalysts is shaped by the synthesis method used here.",
    "Several preparation routes exist for this purpose and give different results.",
    "Subject to the minimization of total free energy, the two metals arrange themselves.",
    "The resulting configuration depends on the relative cohesive energy of the pair.",
    "A catalyst support serves as a carrier for metal dispersion in most systems.",
    "It also imposes electronic and geometric effects on the supported metal particles.",
]


def _boxes() -> list[FlowBox]:
    return [
        FlowBox(1, 38, 60, 250, 80, "2. Multiple Interactions In Catalysts", role="sectionHeading"),
        FlowBox(1, 38, 90, 250, 160, f"{_S[0]} {_S[1]}"),
        FlowBox(1, 38, 170, 250, 185, "2.1. Metal-Metal Interactions", role="sectionHeading"),
        FlowBox(1, 38, 190, 250, 260, f"{_S[2]} {_S[3]}"),
        # No heading role: the numbered form alone has to be enough.
        FlowBox(1, 38, 270, 250, 285, "2.2. Metal-Support Interaction"),
        FlowBox(1, 38, 290, 250, 360, f"{_S[4]} {_S[5]}"),
    ]


def _sentences() -> list[Sentence]:
    return [Sentence(id=f"s{i + 1}", text=t, section="body") for i, t in enumerate(_S)]


def test_headings_start_at_the_sentence_after_them() -> None:
    ordered = order_boxes(_boxes(), _PAGES)
    anchors = heading_anchors(_sentences(), ordered.box_marks)
    assert anchors == [
        {"text": "2. Multiple Interactions In Catalysts", "from": "s1"},
        {"text": "2.1. Metal-Metal Interactions", "from": "s3"},
        {"text": "2.2. Metal-Support Interaction", "from": "s5"},
    ]


def test_order_and_sections_are_unchanged_by_heading_text() -> None:
    plain = [FlowBox(b.page, b.x0, b.y0, b.x1, b.y1, b.text) for b in _boxes()]
    a = order_boxes(_boxes(), _PAGES)
    b = order_boxes(plain, _PAGES)
    assert a.marked_text == b.marked_text
    assert a.sections == b.sections
    assert [(m.start_char, m.openings) for m in a.box_marks] == [
        (m.start_char, m.openings) for m in b.box_marks
    ]


def test_heading_text_rules() -> None:
    assert heading_text(FlowBox(1, 0, 0, 1, 1, "3.4. Strong Alloying Effect in Achieving Alloys"))
    assert not heading_text(FlowBox(1, 0, 0, 1, 1, "2.0"))
    assert not heading_text(FlowBox(1, 0, 0, 1, 1, "1. Smith, J.; Lee, K.; Park, H. 2020."))
    assert heading_text(FlowBox(1, 0, 0, 1, 1, "KEY REFERENCES", role="sectionHeading"))


def test_title_and_supplementary_get_no_heading() -> None:
    ordered = order_boxes(_boxes(), _PAGES)
    sents = _sentences()
    sents[4] = Sentence(id="s5", text=_S[4], section="supplementary")
    sents[5] = Sentence(id="s6", text=_S[5], section="supplementary")
    anchors = heading_anchors(sents, ordered.box_marks, title="2.1. Metal-Metal Interactions")
    assert anchors == [
        {"text": "2. Multiple Interactions In Catalysts", "from": "s1"},
        {"text": "", "from": "s3"},
    ]


def test_clean_headings_shapes_and_bounds() -> None:
    raw = [
        {"text": "", "from": "s0"},
        {"text": "  1.  INTRODUCTION ", "from": "s1"},
        {"text": "x", "from": ""},
        "junk",
        {"text": "y" * 500, "from": "s2"},
    ]
    out = clean_headings(raw)
    assert out[0] == {"text": "1. INTRODUCTION", "from": "s1"}
    assert len(out) == 2 and len(out[1]["text"]) == 200
    assert clean_headings(None) == []


def test_headings_survive_save_and_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    heads = [{"text": "1. INTRODUCTION", "from": "s1"}]
    session = PaperSession(
        title="Heading round trip fixture paper title long enough",
        sentences=_sentences(),
        headings=heads,
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf", doc_role="main")
    assert entry
    loaded, _ = pc.load_cached_session(str(entry["id"]))
    assert loaded.headings == heads
    assert loaded.to_public_dict(include_images=False)["headings"] == heads
    assert PaperSession(title="t").to_public_dict()["headings"] == []
