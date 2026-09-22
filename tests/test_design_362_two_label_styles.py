"""design/362 - read the label the paper printed, and give Scheme its own slot.

Two findings, both measured on the 95-file folder.

The supplementary numbers are printed two ways. ACS, RSC and Elsevier put the `S` on
the number (`Figure S1`); Nature puts it in the word in front (`Supplementary Fig. 1`).
Only the first was read, so `41929_2026_1513_MOESM1_ESM` built 52 slots named
`fig:s1..fig:s33` and `table:s1..table:s19`, its captions all reported `fig:1..fig:33`,
and not one of the 52 met its caption: 52 empty slots and 176 nameless carousel
entries on a paper whose captions are printed one per line.

Schemes were folded into the figure slots, so `Scheme 1` and `Figure 1` - two
different pictures - were stacked in `fig:1`. Three of 88 papers print both.
"""

from __future__ import annotations

import re

from sentence_reading.fig_refs import caption_key, match_figure_index, parse_refs
from sentence_reading.pdf.caption_pairing import (
    _slot_label_pattern,
    pair_slot_captions,
    refill_empty_slots,
)
from sentence_reading.pdf.composite import (
    slot_kind_word,
    slot_missing_caption,
    slot_unnumbered_caption,
)
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    build_slot_plan,
    initial_body_assignments,
    slot_key_from_caption_key,
)


def _box(
    bid: str,
    kind: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    text: str = "",
    page: int = 0,
) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=page,
        kind=kind,
        rect={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        text=text,
    )


def _layout(boxes: list[LayoutBox], pages: int = 1) -> LayoutMap:
    return LayoutMap(
        pages=[{"width": 595.0, "height": 842.0} for _ in range(pages)],
        boxes=boxes,
    )


# ---------------------------------------------------------------- label styles


def test_natures_word_carries_the_same_s_as_acss_number() -> None:
    assert caption_key("Supplementary Fig. 1. Ni K-edge XANES") == "fig:s1"
    assert caption_key("Figure S1. TEM images") == "fig:s1"
    assert caption_key("Supplementary Table 7. Ammoxidation yields") == "table:s7"
    assert caption_key("Table S7. Ammoxidation yields") == "table:s7"


def test_a_plain_number_stays_a_plain_number() -> None:
    assert caption_key("Fig. 2 Cycling stability") == "fig:2"
    assert caption_key("Table 3 Measured yields") == "table:3"
    assert caption_key("Figure 12. XRD patterns") == "fig:12"


def test_the_other_spellings_of_the_word_are_read_too() -> None:
    assert caption_key("Supporting Figure 2. X-ray data") == "fig:s2"
    assert caption_key("Supplemental Table 5. Rate constants") == "table:s5"


def test_a_supplementary_label_is_not_offered_to_the_main_paper() -> None:
    # `Supplementary Table 1` must not be handed to the main paper's `table:1`.
    assert slot_key_from_caption_key("table:s1") is None
    assert slot_key_from_caption_key("table:s1", supplementary=True) == "table:s1"


def test_the_body_now_tells_the_two_fours_apart() -> None:
    refs = parse_refs("As Supplementary Fig. 4 and Fig. 4 both show, the yield rose.")
    assert refs == ["Supplementary Fig. 4", "Fig. 4"]


def test_a_panel_of_a_supplementary_figure_keeps_the_s() -> None:
    assert parse_refs("see Supplementary Fig. 4(B)") == ["Supplementary Fig. 4"]


def test_the_search_pattern_accepts_both_styles() -> None:
    pat = _slot_label_pattern("fig:s1")
    assert pat is not None
    assert pat.match("Supplementary Fig. 1. Ni K-edge")
    assert pat.match("Figure S1. TEM images")
    # A different number must not answer.
    assert not pat.match("Supplementary Fig. 12. XRD")
    assert not pat.match("Figure S12. XRD")
    # A main-paper caption must not answer a supplementary slot.
    assert not pat.match("Figure 1. Reaction profile")


def test_a_main_slot_does_not_answer_to_the_supplementary_word() -> None:
    pat = _slot_label_pattern("table:1")
    assert pat is not None
    assert pat.match("Table 1 Measured yields")
    assert not pat.match("Supplementary Table 1. Surface composition")


def test_a_nature_style_si_pairs_every_slot() -> None:
    # The shape of `41929_2026_1513_MOESM1_ESM`: label boxes Azure tagged
    # `paragraph`, a picture above each figure caption, a grid below each table one.
    boxes = [
        _box("f-body", "figure_body", 60, 100, 520, 400, page=0),
        _box(
            "f-cap",
            "paragraph",
            60,
            410,
            520,
            430,
            "Supplementary Fig. 1. Ni K-edge XANES of the fresh catalyst.",
            page=0,
        ),
        _box(
            "t-cap",
            "paragraph",
            60,
            100,
            520,
            120,
            "Supplementary Table 1. Surface composition of each sample.",
            page=1,
        ),
        _box("t-body", "table_body", 60, 130, 520, 400, page=1),
    ]
    layout = _layout(boxes, pages=2)
    plan = build_slot_plan(layout, supplementary=True)
    assert [s.key for s in plan.slots] == ["fig:s1", "table:s1"]
    initial_body_assignments(layout, plan, supplementary=True)
    pair_slot_captions(layout, plan)
    refill_empty_slots(layout, plan)
    assert [s.status for s in plan.slots] == ["filled", "filled"]


# -------------------------------------------------------------------- schemes


def test_a_scheme_gets_its_own_slot_key() -> None:
    assert slot_key_from_caption_key("scheme:1") == "scheme:1"
    assert slot_key_from_caption_key("scheme:2a") == "scheme:2"
    assert slot_key_from_caption_key("scheme:s1", supplementary=True) == "scheme:s1"


def test_scheme_one_and_figure_one_are_two_slots() -> None:
    boxes = [
        _box("s-body", "figure_body", 60, 100, 520, 300, page=0),
        _box(
            "s-cap",
            "figure_caption",
            60,
            310,
            520,
            330,
            "Scheme 1. Proposed reaction pathway.",
            page=0,
        ),
        _box("f-body", "figure_body", 60, 400, 520, 640, page=0),
        _box(
            "f-cap",
            "figure_caption",
            60,
            650,
            520,
            670,
            "Figure 1. Measured conversion over time.",
            page=0,
        ),
    ]
    layout = _layout(boxes)
    plan = build_slot_plan(layout)
    assert [s.key for s in plan.slots] == ["fig:1", "scheme:1"]
    initial_body_assignments(layout, plan)
    pair_slot_captions(layout, plan)
    refill_empty_slots(layout, plan)
    by_key = {s.key: s for s in plan.slots}
    assert by_key["fig:1"].body_box_ids == ["f-body"]
    assert by_key["scheme:1"].body_box_ids == ["s-body"]
    # The one thing the fold did: two unrelated pictures in one slot.
    bodies = [bid for s in plan.slots for bid in s.body_box_ids]
    assert len(bodies) == len(set(bodies))


def test_a_scheme_slot_is_searched_among_figures_not_tables() -> None:
    pat = _slot_label_pattern("scheme:2")
    assert pat is not None
    assert pat.match("Scheme 2 Synthesis of the support.")
    assert not pat.match("Figure 2 Synthesis of the support.")
    assert not pat.match("Table 2 Synthesis of the support.")


def test_a_scheme_is_labelled_a_scheme() -> None:
    assert slot_kind_word("scheme") == "Scheme"
    assert slot_missing_caption("scheme", 3) == "Scheme 3 (missing)"
    assert slot_unnumbered_caption("scheme") == "번호 없는 반응식"
    # The other two kinds keep the words they had.
    assert slot_missing_caption("table", 2) == "Table 2 (missing)"
    assert slot_missing_caption("fig", 2) == "Figure 2 (missing)"


def test_the_carousel_keeps_figures_then_schemes_then_tables() -> None:
    from sentence_reading.pdf.extract import _slot_sort_key

    keys = ["table:1", "scheme:2", "fig:3", "scheme:1", "fig:1"]
    assert sorted(keys, key=_slot_sort_key) == [
        "fig:1",
        "fig:3",
        "scheme:1",
        "scheme:2",
        "table:1",
    ]


def test_a_scheme_reference_reaches_the_scheme_not_the_figure() -> None:
    figures = [
        {"slot_key": "fig:1", "caption": "Figure 1. Measured conversion."},
        {"slot_key": "scheme:1", "caption": "Scheme 1. Proposed pathway."},
    ]
    assert match_figure_index(figures, "Figure 1") == 0
    assert match_figure_index(figures, "Scheme 1") == 1


def test_a_paper_ingested_before_this_still_finds_its_scheme() -> None:
    # Papers already in the cache stored their schemes under `fig:N`.
    figures = [{"slot_key": "fig:1", "caption": "Scheme 1. Proposed pathway."}]
    assert match_figure_index(figures, "Scheme 1") == 0


def test_the_label_patterns_are_anchored_to_the_start() -> None:
    # A sentence that merely mentions a label is not that label's caption.
    for key in ("fig:1", "scheme:1", "table:1", "fig:s1"):
        pat = _slot_label_pattern(key)
        assert pat is not None
        assert not pat.match("As shown in Figure 1, the rate falls.")
        assert not pat.match("The data in Table 1 and Scheme 1 agree.")


def test_no_slot_key_is_built_from_an_unknown_kind() -> None:
    assert slot_key_from_caption_key("chart:1") is None
    assert slot_key_from_caption_key("") is None
    assert slot_key_from_caption_key("fig") is None


def test_every_slot_key_matches_the_kind_it_claims() -> None:
    pat = re.compile(r"^(fig|scheme|table):s?\d+$")
    for ckey, want in (
        ("fig:3a", "fig:3"),
        ("scheme:4b", "scheme:4"),
        ("table:12", "table:12"),
    ):
        sk = slot_key_from_caption_key(ckey)
        assert sk == want
        assert pat.match(sk)
