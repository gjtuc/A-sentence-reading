"""Azure box reading order — synthetic geometry, no live call."""

from sentence_reading.pdf.section_flow import FlowBox, header_key, order_boxes


def _page() -> list[dict]:
    return [{"width": 595.0, "height": 792.0}, {"width": 595.0, "height": 792.0}]


def test_marked_chunks_keep_the_header_section() -> None:
    from sentence_reading.llm.debone import chunk_raw_text
    from sentence_reading.pdf.section_flow import pinned_section

    text = (
        "<<<ASR_SECTION results>>>\n"
        + ("Results prose. " * 400)
        + "\n\n<<<ASR_SECTION conclusion>>>\nClosing."
    )
    chunks = chunk_raw_text(text, size=500)
    assert chunks
    assert {pinned_section(c) for c in chunks} == {"results", "conclusion"}
    assert all(pinned_section(c) != "discussion" for c in chunks)
    assert header_key("3. Results and discussions") == "results"
    assert header_key("2.1 Material synthesis") is None
    assert header_key("4. Conclusion") == "conclusion"
    assert header_key("Discussion") == "discussion"


def test_abstract_sidebar_before_introduction_and_chrome_dropped() -> None:
    boxes = [
        FlowBox(0, 300, 40, 520, 90, "Renewable Energy journal", role="pageHeader"),
        FlowBox(0, 38, 161, 482, 190, "High-performance cathode materials", role="title"),
        FlowBox(0, 38, 206, 400, 230, "A. Author, B. Author"),
        FlowBox(0, 38, 250, 180, 280, "ARTICLE INFO"),
        FlowBox(0, 202, 269, 259, 286, "ABSTRACT"),
        FlowBox(0, 202, 288, 560, 370, "High-performance cathode body starts here."),
        FlowBox(0, 38, 269, 160, 286, "Keywords: foo"),
        FlowBox(0, 38, 394, 180, 410, "1. Introduction"),
        FlowBox(0, 38, 420, 250, 500, "Left introduction prose."),
        FlowBox(0, 307, 420, 560, 500, "Right introduction prose."),
        FlowBox(0, 38, 730, 400, 760, "Copyright 2025 Elsevier Ltd."),
    ]
    ordered = order_boxes(boxes, _page())
    keys = [k for k, _ in ordered.sections]
    assert keys[:3] == ["title", "abstract", "introduction"]
    assert "discussion" not in keys
    joined = ordered.marked_text
    assert "Author" not in joined
    assert "ARTICLE INFO" not in joined
    assert "Keywords" not in joined
    assert "Elsevier" not in joined
    assert "Renewable Energy" not in joined
    abs_i = joined.index("High-performance cathode body")
    left_i = joined.index("Left introduction")
    right_i = joined.index("Right introduction")
    assert abs_i < left_i < right_i
    assert "<<<ASR_SECTION introduction>>>" in joined


def test_experimental_keeps_right_column_top_after_left_header() -> None:
    boxes = [
        FlowBox(0, 38, 100, 220, 120, "1. Introduction"),
        FlowBox(0, 38, 130, 250, 180, "Intro body."),
        FlowBox(1, 38, 80, 250, 120, "End of introduction."),
        FlowBox(1, 38, 261, 220, 280, "2. Experimental"),
        FlowBox(1, 38, 429, 250, 500, "2.2 Synthesis text"),
        FlowBox(1, 307, 50, 560, 110, "followed by co-sintering"),
        FlowBox(1, 307, 129, 560, 200, "2.3 later step"),
    ]
    ordered = order_boxes(boxes, _page())
    text = ordered.marked_text
    assert text.index("End of introduction.") < text.index("2.2 Synthesis text")
    assert text.index("2.2 Synthesis text") < text.index("followed by co-sintering")
    assert text.index("followed by co-sintering") < text.index("2.3 later step")
    assert ordered.sections[-1][0] == "experimental"


def test_references_are_not_a_practice_section() -> None:
    boxes = [
        FlowBox(0, 38, 80, 250, 100, "4. Conclusion"),
        FlowBox(0, 38, 110, 250, 160, "iso-valence closing prose."),
        FlowBox(0, 38, 200, 250, 220, "Acknowledgement"),
        FlowBox(0, 38, 230, 250, 260, "We thank the lab."),
        FlowBox(0, 307, 80, 560, 100, "References"),
        FlowBox(0, 307, 110, 560, 160, "[1] A. Cite."),
    ]
    ordered = order_boxes(boxes, _page()[:1])
    keys = [k for k, _ in ordered.sections]
    assert "references" not in keys
    assert "discussion" not in keys
    assert "We thank the lab." in ordered.marked_text
    assert ordered.references_text.startswith("References")
    assert "[1]" in ordered.references_text
    assert "[1]" not in "\n".join(text for _k, text in ordered.sections)


def test_column_break_does_not_leave_short_fragments() -> None:
    from sentence_reading.pdf.section_flow import join_section_text

    joined = join_section_text(
        [
            "3.1.",
            "Crystal structure",
            "The corresponding results are",
            "Listed in Table 3.",
            "R = k (pO2) (3)",
            "Where k is a constant.",
        ]
    )
    assert "3.1 Crystal structure" in joined
    assert "The corresponding results are Listed in Table 3." in joined
    assert "(3)" not in joined
    assert "Where k is a constant." in joined


def test_further_analysis_heading_is_discussion() -> None:
    from sentence_reading.pdf.section_flow import header_key

    assert header_key("4. Further analysis and discussion") == "discussion"
    assert header_key("3. Results and discussions") == "results"
    assert header_key("1. Okumura, Y. Nose, J. 2020.") is None


def test_footnote_bibliography_stays_in_references() -> None:
    boxes = [
        FlowBox(0, 36, 542, 250, 560, "5. Conclusions"),
        FlowBox(0, 36, 570, 250, 640, "The cell remained stable."),
        FlowBox(0, 305, 532, 520, 548, "References"),
        FlowBox(0, 309, 551, 520, 575, "[1] Y. Okumura, A journal. 2020.", role="ParagraphRole.FOOTNOTE"),
        FlowBox(0, 309, 700, 400, 720, "Corresponding author footnote.", role="ParagraphRole.FOOTNOTE"),
    ]
    ordered = order_boxes(boxes, _page()[:1])
    assert "[1]" in ordered.references_text
    assert "Corresponding author" not in ordered.references_text
    assert "[1]" not in "\n".join(text for _k, text in ordered.sections)


def test_broken_equation_is_not_a_sentence() -> None:
    from sentence_reading.pdf.section_flow import join_section_text

    joined = join_section_text(
        [
            "Agreement with previous reports [33].",
            "tion =",
            "O 2 = exp AHhydr RT Khydr exp",
            "We further analyze the data based on the model.",
        ]
    )
    assert "tion" not in joined
    assert "AHhydr" not in joined
    assert "We further analyze the data based on the model." in joined


def test_design_332_headingless_reference_list_is_not_practice() -> None:
    """Wiley prints the numbered list with no `References` line."""
    from sentence_reading.pdf.section_flow import _retag_bibliography_runs

    class _B:
        def __init__(self, text: str) -> None:
            self.text = text

    assigned = [
        ("introduction", _B("The catalyst was stable over the whole run.")),
        ("acknowledgement", _B("Acknowledgements")),
        ("acknowledgement", _B("We thank the funding agency for support.")),
        ("acknowledgement", _B("[1] A. Author, B. Author, Adv. Mater. 2019, 31, 1.")),
        ("acknowledgement", _B("[2] C. Author, D. Author, Nature 2020, 5, 22.")),
        ("acknowledgement", _B("[3] E. Author, Science 2021, 7, 90.")),
    ]
    out = _retag_bibliography_runs(assigned)
    keys = [k for k, _ in out]
    assert keys[0] == "introduction"
    assert keys[1] == "acknowledgement"
    assert keys[2] == "acknowledgement"
    # All three list entries end up in references, including the first.
    assert keys[3:] == ["references", "references", "references"]


def test_design_332_a_single_numbered_line_is_not_a_reference_list() -> None:
    from sentence_reading.pdf.section_flow import _retag_bibliography_runs

    class _B:
        def __init__(self, text: str) -> None:
            self.text = text

    assigned = [
        ("results", _B("[1] A. Author, B. Author, Adv. Mater. 2019, 31, 1.")),
        ("results", _B("Conversion rose steadily with temperature.")),
    ]
    keys = [k for k, _ in _retag_bibliography_runs(assigned)]
    assert keys == ["results", "results"]


def test_design_332_a_heading_after_the_list_stops_the_run() -> None:
    """A journal that prints Methods after References must recover.

    This pass only retags the bibliography run; `_read_page` still owns the key,
    so the assertion is that the heading and its body leave references, not that
    the key is re-derived here.
    """
    from sentence_reading.pdf.section_flow import _retag_bibliography_runs

    class _B:
        def __init__(self, text: str) -> None:
            self.text = text

    assigned = [
        ("body", _B("[1] A. Author, Adv. Mater. 2019, 31, 1.")),
        ("body", _B("[2] B. Author, Nature 2020, 5, 22.")),
        ("methods", _B("Methods")),
        ("methods", _B("Samples were calcined at 800 C for two hours.")),
    ]
    keys = [k for k, _ in _retag_bibliography_runs(assigned)]
    assert keys[:2] == ["references", "references"]
    assert "references" not in keys[2:]


def test_design_325_abstract_run_in_headings_open_a_section() -> None:
    from sentence_reading.pdf.section_flow import header_key

    # Azure returns the abstract as one long paragraph, so the run-in form has
    # to be decided before the standalone-heading length guard.
    springer = (
        "Abstract\u2212In order to increase the performance of fuel cell "
        "electrode, carbon nanotubes were used as support instead of "
        "conventional carbon black and the text keeps going past the guard"
    )
    acs = (
        "ABSTRACT: A series of bimetallic Fe-Ni catalysts with ratios between "
        "0 and 1.5 have been examined for methane dry reforming at temperature"
    )
    assert header_key(springer) == "abstract"
    assert header_key(acs) == "abstract"
    assert header_key("Abstract\u2013 This paper reports") == "abstract"
    assert header_key("Abstract\u2014This paper reports") == "abstract"
    assert header_key("Abstract") == "abstract"
    # Elsevier letter-spaces the heading, like `a r t i c l e   i n f o`.
    assert header_key("A B S T R A C T") == "abstract"


def test_design_325_abstract_word_in_prose_is_not_a_heading() -> None:
    from sentence_reading.pdf.section_flow import header_key

    assert header_key("Abstract reasoning is not a heading and this runs on") is None
    assert header_key("Abstracts of the reviewed works are summarised below.") is None
