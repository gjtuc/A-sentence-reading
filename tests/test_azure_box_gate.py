"""design/302 — do not edit reading order until these gates pass."""

from sentence_reading.pdf.azure_box_gate import (
    fixture_report,
    inventory_row,
    role_parse_ok,
)
from sentence_reading.pdf.section_flow import FlowBox


def test_enum_role_must_be_stripped() -> None:
    assert role_parse_ok(["ParagraphRole.PAGE_HEADER", "ParagraphRole.TITLE"])
    assert not role_parse_ok(["ParagraphRole.PAGE_HEADER.still"])
    assert not role_parse_ok(["page_header"])


def test_inventory_has_no_paper_text() -> None:
    row = inventory_row(FlowBox(0, 1, 2, 3, 4, "High-performance secret prose", role="title"))
    assert "text" not in row
    assert "High-performance" not in str(row)
    assert row["n"] == len("High-performance secret prose")


def test_locked_azure_geometry() -> None:
    report = fixture_report()
    assert report["role_parse_ok"]
    assert report["abstract_before_intro"]
    assert report["enum_footer_dropped"]
    assert report["exp_right_top"]
    assert report["refs_not_practice"]
