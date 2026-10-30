# -*- coding: utf-8 -*-
"""design/488 - program-made Info titles, non-Latin titles, a title font above the body."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from sentence_reading import title_replay as tr


def test_a_program_prefix_or_suffix_comes_off() -> None:
    assert tr.clean_info_title("Microsoft PowerPoint - Lecture 4 schedule") == "Lecture 4 schedule"
    assert tr.clean_info_title("Thesis plan guide (students) - Google Docs") == (
        "Thesis plan guide (students)"
    )


def test_a_file_name_or_a_default_name_is_dropped() -> None:
    assert tr.clean_info_title("Microsoft Word - review 0.docx") == ""
    assert tr.clean_info_title("LPH-300LV_Leather.pdf") == ""
    assert tr.clean_info_title("PowerPoint 프레젠테이션") == ""
    assert tr.clean_info_title("Untitled document") == ""


def test_a_review_file_takes_its_top_block() -> None:
    picked, source = tr.pick_session_title(
        info_title="Microsoft Word - review 0.docx",
        filename="41467_2021_24079_MOESM2_ESM.pdf",
        text="REVIEWER COMMENTS\n\nReviewer #1 (Remarks to the Author):\n\nThe authors report",
    )
    assert (picked, source) == ("REVIEWER COMMENTS", "head")


def test_a_korean_title_is_not_chrome() -> None:
    title = "국가전략기술 체계 고도화 방향(안)"
    assert not tr.is_title_chrome(title)
    assert tr.title_usable(title)


def test_dates_form_fields_and_notes_are_chrome() -> None:
    assert tr.is_title_chrome("2026년 08월 20일 (목)")
    assert tr.is_title_chrome("2026. 08. 28.(금)")
    assert tr.is_title_chrome("( 법인사업자:본점) 등록번호: 314-82-02242")
    assert tr.is_title_chrome("* 본 증명의 위·변조 여부는 발급일로부터 확인")
    assert not tr.is_title_chrome("Blue hydrogen: Current status and future technologies")


def test_body_size_counts_characters() -> None:
    lines = [(18.0, "Short title here"), (9.0, "x" * 400), (9.2, "y" * 100)]
    assert tr.body_font_size(lines) == 9.0


def test_no_line_above_the_body_gives_no_styled_title() -> None:
    lines = [(9.0, "REVIEWER COMMENTS"), (9.0, "Reviewer #1 (Remarks to the Author): the work")]
    assert tr.join_largest_title_lines(lines, min_size=9.0 * tr.TITLE_FONT_RATIO) == ""


def _pdf(path: Path, pages: list[list[tuple[float, str]]]) -> Path:
    doc = pymupdf.open()
    for rows in pages:
        page = doc.new_page()
        y = 72.0
        for size, text in rows:
            page.insert_text((72, y), text, fontsize=size)
            y += size * 1.6
    doc.save(path)
    doc.close()
    return path


def test_a_sparse_cover_page_keeps_its_title(tmp_path) -> None:
    body = [(10.0, "Body text of the manual goes on for a while here.")] * 30
    pdf = _pdf(
        tmp_path / "manual.pdf",
        [[(8.0, "Prepared by someone"), (16.0, "Instrument Software Version 7"),
          (16.0, "Training Manual")], body, body],
    )
    assert tr.pdf_styled_title(pdf) == "Instrument Software Version 7 Training Manual"


def test_one_size_everywhere_gives_no_styled_title(tmp_path) -> None:
    rows = [(9.0, "REVIEWER COMMENTS")] + [(9.0, "Reviewer one asked for more data.")] * 30
    assert tr.pdf_styled_title(_pdf(tmp_path / "review.pdf", [rows, rows])) == ""
