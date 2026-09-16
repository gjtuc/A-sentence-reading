"""Session title uses Info.Title or the SI head paragraph, not the Elsevier stem."""

from __future__ import annotations

from sentence_reading.cache.paper_cache import normalize_pairing_key
from sentence_reading.models import Sentence
from sentence_reading.title_replay import join_largest_title_lines, pick_session_title

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
