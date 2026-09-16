"""Session title uses Info.Title or the SI head paragraph, not the Elsevier stem."""

from __future__ import annotations

from sentence_reading.cache.paper_cache import normalize_pairing_key
from sentence_reading.models import Sentence
from sentence_reading.title_replay import (
    align_title_sentences,
    join_largest_title_lines,
    pick_session_title,
    title_from_azure_paragraphs,
    title_from_docx_paragraphs,
)

PAPER = (
    "Evaluation of calcium doped Ba-Co-Nb-O perovskite as cathode materials "
    "for intermediate-temperature solid oxide fuel cells"
)


def test_info_title_beats_author_section_and_stem() -> None:
    title, source = pick_session_title(
        info_title=PAPER,
        filename="1-s2.0-S0960148125003246-main.pdf",
        sentences=[
            Sentence(
                id="a",
                text="TongYuan Xu, Chao Huang, Liping Sun * ABSTRACT Keywords:",
                section="title",
            )
        ],
        title_guess="TongYuan Xu, Chao Huang *",
    )
    assert source == "info"
    assert title == PAPER


def test_si_banner_uses_next_paragraph_not_mmc_stem() -> None:
    text = f"Supporting Information\n\n{PAPER}\n\nTongYuan Xu, Chao Huang"
    title, source = pick_session_title(
        info_title="Supporting Information",
        filename="1-s2.0-S0960148125003246-mmc1.docx",
        text=text,
        sentences=[Sentence(id="a", text=PAPER, section="supplementary")],
    )
    assert source == "head"
    assert title == PAPER
    main, _ = pick_session_title(
        info_title=PAPER,
        filename="1-s2.0-S0960148125003246-main.pdf",
    )
    assert normalize_pairing_key(title) == normalize_pairing_key(main)
    assert normalize_pairing_key(title)


def test_styled_lines_join_title_not_authors() -> None:
    joined = join_largest_title_lines(
        [
            (13.4, "Evaluation of calcium doped Ba-Co-Nb-O perovskite as cathode materials"),
            (13.4, "for intermediate-temperature solid oxide fuel cells"),
            (10.6, "TongYuan Xu , Chao Huang , Liping Sun *"),
            (7.0, "A B S T R A C T"),
        ]
    )
    assert joined == PAPER
    title, source = pick_session_title(
        info_title="",
        filename="1-s2.0-S0960148125003246-main.pdf",
        styled_title=joined,
        sentences=[
            Sentence(id="a", text="A B S T R A C T High-performance cathode", section="title")
        ],
    )
    assert source == "styled"
    assert title == PAPER


def test_title_card_replaces_author_chrome_and_drops_ko() -> None:
    chrome = (
        "TongYuan Xu, Chao Huang, Liping Sun *, Lihua Huo, Hui Zhao "
        "ARTICLE INFO ABSTRACT Keywords: Solid oxide fuel cells"
    )
    rows, card = align_title_sentences(
        [
            Sentence(id="t", text=chrome, section="title", text_ko="저자 덩어리"),
            Sentence(id="a", text="The cathode is stable.", section="abstract", text_ko="안정하다."),
        ],
        PAPER,
    )
    assert card == "replaced"
    assert rows[0].section == "title"
    assert rows[0].text == PAPER
    assert rows[0].text_ko == ""
    assert rows[1].text_ko == "안정하다."


def test_usable_title_card_keeps_translation() -> None:
    rows, card = align_title_sentences(
        [Sentence(id="t", text=PAPER, section="title", text_ko="공식 제목")],
        PAPER,
    )
    assert card == "kept"
    assert rows[0].text_ko == "공식 제목"


def test_first_paragraph_is_the_title_when_there_is_no_banner() -> None:
    raw = f"Supplementary Materials\n\n{PAPER}\n\nLulu Jiang 1, Donglin Han 1*"
    stripped = f"{PAPER}\n\nFig. S1 XRD patterns of the sintered pellets."
    kept_head, kept_source = pick_session_title(
        info_title="",
        filename="1-s2.0-S1385894724017960-mmc1.docx",
        text=stripped,
    )
    assert kept_source == "head"
    assert kept_head == PAPER
    kept, kept_source = pick_session_title(
        info_title="Supplementary Materials",
        filename="1-s2.0-S1385894724017960-mmc1.docx",
        text=raw,
    )
    assert kept_source == "head"
    assert kept == PAPER
    also, also_source = pick_session_title(
        info_title="",
        filename="1-s2.0-S2095809922003708-mmc1.docx",
        text=f"Supplementary Information for\n\n{PAPER}",
    )
    assert also_source == "head"
    assert also == PAPER


def test_manuscript_id_and_journal_masthead_are_not_the_title() -> None:
    article = "Synthetic nickel catalyst study for methane dry reforming"
    title, source = pick_session_title(
        info_title="cs5b00357 1..12",
        filename="cs5b00357.pdf",
        styled_title=article,
    )
    assert source == "styled"
    assert title == article
    joined = join_largest_title_lines(
        [
            (22.0, "Catalysis Science & Technology"),
            (14.0, "Recent advances in promoting dry reforming of"),
            (14.0, "methane using nickel-based catalysts"),
            (9.0, "Haibin Zhu"),
        ]
    )
    assert joined == (
        "Recent advances in promoting dry reforming of methane using nickel-based catalysts"
    )


def test_html_entity_and_si_banner_are_not_kept_as_the_title() -> None:
    title, source = pick_session_title(
        info_title="Metal&#x2013;support interactions in a synthetic catalyst study",
        filename="d4cs00527a.pdf",
    )
    assert source == "info"
    assert "\u2013" in title
    assert "&#x" not in title
    joined = join_largest_title_lines(
        [
            (16.0, "Supporting Online Material for"),
            (14.0, "The Origin of OB Runaway Stars"),
            (11.0, "Michiko S. Fujii"),
        ]
    )
    assert joined == "The Origin of OB Runaway Stars"


def test_azure_wrapped_title_keeps_the_same_size_next_line() -> None:
    class _Region:
        def __init__(self, y0: float, y1: float) -> None:
            self.page_number = 1
            self.polygon = [0, y0, 5, y0, 5, y1, 0, y1]

    class _Para:
        def __init__(self, role: str, content: str, y0: float, y1: float) -> None:
            self.role = role
            self.content = content
            self.bounding_regions = [_Region(y0, y1)]

    first = "Evaluation of a synthetic perovskite as cathode"
    second = "materials for intermediate-temperature solid oxide fuel cells"
    picked = title_from_azure_paragraphs(
        [
            _Para("ParagraphRole.TITLE", first, 1.53, 1.75),
            _Para("ParagraphRole.SECTION_HEADING", second, 2.39, 2.61),
            _Para("None", "Tong Yuan Xu, Chao Huang, Liping Sun*", 2.97, 4.02),
        ]
    )
    assert picked == f"{first} {second}"
    title, source = pick_session_title(
        azure_title=first,
        styled_title="",
        text=f"Supporting Information\n\n{first} {second}",
        filename="sample-mmc1.docx",
    )
    assert source == "head"
    assert title == f"{first} {second}"
    rich, rich_source = pick_session_title(
        azure_title="Protonic conductivity of grain boundaries in BaZr0.9 Y0.103-6",
        styled_title="Protonic conductivity of grain boundaries in BaZr0.9Y0.1O3-\u03b4",
        filename="sample-mmc1.docx",
    )
    assert rich_source == "styled"
    assert "\u03b4" in rich


def test_azure_enum_title_role_beats_a_journal_info_title() -> None:
    class _Region:
        page_number = 1

    class _Para:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content
            self.bounding_regions = [_Region()]

    article = "Synthetic nickel catalyst study for methane dry reforming"
    picked = title_from_azure_paragraphs(
        [
            _Para("ParagraphRole.PAGE_HEADER", "Catalysis Science & Technology"),
            _Para("ParagraphRole.TITLE", article),
        ]
    )
    assert picked == article
    title, source = pick_session_title(
        info_title="Catalysis Science & Technology",
        filename="d3cy01612a.pdf",
        azure_title=picked,
        styled_title="Catalysis Science & Technology",
    )
    assert source == "azure"
    assert title == article


def test_publisher_ids_fall_through_and_near_font_lines_join() -> None:
    article = (
        "Hydrodesulfurization of Dibenzothiophene and 4, 6-Dimethyldibenzothiophene "
        "Using Fluorinated NiMoS Catalysts"
    )
    joined = join_largest_title_lines(
        [
            (8.9, "Science and Technology in Catalysis 2002"),
            (17.7, "66"),
            (18.7, "Hydrodesulfurization of Dibenzothiophene"),
            (18.7, "and 4, 6-Dimethyldibenzothiophene Using"),
            (17.7, "Fluorinated NiMoS Catalysts"),
            (9.2, "Heeyeon KIM, Jung Joon LEE, Jae Hyun KOH and Sang Heup MOON*"),
        ]
    )
    assert joined == article
    title, source = pick_session_title(
        info_title="PII: S0167-2991(03)80223-9",
        filename="s0167-2991.pdf",
        styled_title=joined,
    )
    assert source == "styled"
    assert title == article
    ranged, ranged_source = pick_session_title(
        info_title="acs_nn_nn-2015-00678j 1..11",
        filename="acsnano.5b00678.pdf",
        styled_title="Resilient platinum nanocatalysts with a porous graphene envelope",
    )
    assert ranged_source == "styled"
    framed, framed_source = pick_session_title(
        info_title="[04] 541-548 sample.fm",
        filename="kcers.pdf",
        styled_title="Synthesis of oxide nanorods and their application as membrane materials",
    )
    assert framed_source == "styled"


def test_page_label_does_not_steal_the_title_from_a_nearby_font() -> None:
    article = "Optimizing a nickel copper ratio in nanoparticle catalysts for methane dry reforming"
    joined = join_largest_title_lines(
        [
            (9.0, "S-1"),
            (12.0, "Supporting Information"),
            (10.0, article),
            (10.0, "Kaihang Han,1,2 Shuo Wang,1 Qiying Liu,2* Fagen Wang1,2,3*"),
            (6.97, "Temperature (K)"),
        ]
    )
    assert joined == article


def test_repeated_kicker_and_issue_citation_are_not_the_title() -> None:
    title, source = pick_session_title(
        info_title=(
            "Alloyed Particles: Low-temperature synthesis of alloyed particles "
            "for oxygen reduction (Adv. Mater. 33/2016)"
        ),
        filename="cover.pdf",
        styled_title="www.advmat.de",
    )
    assert source == "info"
    assert title == "Low-temperature synthesis of alloyed particles for oxygen reduction"


def test_word_title_style_beats_a_filename() -> None:
    class _Style:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Para:
        def __init__(self, style: str, text: str) -> None:
            self.style = _Style(style)
            self.text = text

    article = "Synthetic oxide title for oxygen reduction reaction"
    picked = title_from_docx_paragraphs(
        [
            _Para("Normal", "Supplementary Information"),
            _Para("htitle", article),
            _Para("hauthors", "A Person, B Person*"),
        ]
    )
    assert picked == article
    title, source = pick_session_title(
        filename="smll71948-sup-0001-suppmat.docx",
        styled_title=picked,
        text="Supplementary Information\n\nA caption that is not the title.",
    )
    assert source == "styled"
    assert title == article


def test_publisher_file_id_is_not_a_title_and_caption_is_skipped() -> None:
    title, source = pick_session_title(
        filename="smll71948-sup-0001-suppmat.docx",
        text=(
            "A synthetic oxide title for oxygen reduction reaction\n\n"
            "Fig. S1 Powder patterns of the sintered pellets."
        ),
    )
    assert source == "head"
    assert title == "A synthetic oxide title for oxygen reduction reaction"
    skipped, skipped_source = pick_session_title(
        filename="sample-mmc1.docx",
        text="Fig. S1 Powder patterns of the sintered pellets.",
    )
    assert skipped_source == "stem_fallback"
