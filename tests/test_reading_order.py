"""다단 reading order (0.2.32 · design/31)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.extract_quality import QualityDecision
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.reading_order import (
    merge_multicolumn_decision,
    reorder_blocks_two_column,
)


def test_status() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.40"
    assert st.get("reading_order") is True
    assert PIPELINE_VERSION == "rich-v10"
    assert st["pipeline_version"] == "rich-v10"


def test_reorder_two_column_left_then_right() -> None:
    # 페이지 폭 200: 왼쪽 x~20, 오른쪽 x~120 — 세로로 섞여 있어도 좌열 먼저
    blocks = [
        (10.0, 10.0, 80.0, 30.0, "L1"),
        (110.0, 10.0, 180.0, 30.0, "R1"),
        (10.0, 40.0, 80.0, 60.0, "L2"),
        (110.0, 40.0, 180.0, 60.0, "R2"),
        (10.0, 70.0, 80.0, 90.0, "L3"),
        (110.0, 70.0, 180.0, 90.0, "R3"),
    ]
    out = reorder_blocks_two_column(blocks, page_width=200.0)
    assert out.is_multicolumn is True
    assert out.reordered is True
    # 좌 전체 후 우
    assert out.text.index("L1") < out.text.index("L2") < out.text.index("L3")
    assert out.text.index("L3") < out.text.index("R1")
    assert out.text.index("R1") < out.text.index("R2") < out.text.index("R3")


def test_single_column_not_multicolumn() -> None:
    blocks = [
        (10.0, 10.0, 180.0, 30.0, "A only line one here"),
        (10.0, 40.0, 180.0, 60.0, "B only line two here"),
        (10.0, 70.0, 180.0, 90.0, "C only line three xx"),
        (10.0, 100.0, 180.0, 120.0, "D only line four xx"),
    ]
    out = reorder_blocks_two_column(blocks, page_width=200.0)
    assert out.is_multicolumn is False


def test_edge_empty_and_narrow() -> None:
    empty = reorder_blocks_two_column([], page_width=100.0)
    assert empty.text == ""
    assert empty.is_multicolumn is False
    # 블록 부족
    few = reorder_blocks_two_column(
        [(0, 0, 10, 10, "a1"), (50, 0, 60, 10, "b1")],
        page_width=100.0,
    )
    assert few.is_multicolumn is False
    # page_width 0 → bbox 로 추정해도 크래시 없음
    ok = reorder_blocks_two_column(
        [
            (0, 0, 40, 10, "left aa"),
            (60, 0, 100, 10, "right bb"),
            (0, 20, 40, 30, "left cc"),
            (60, 20, 100, 30, "right dd"),
        ],
        page_width=0.0,
    )
    assert isinstance(ok.text, str)


def test_merge_multicolumn_forces_repair() -> None:
    base = QualityDecision(verdict="text_ok", bad_pages=[], source="heuristic")
    merged = merge_multicolumn_decision(base, [1, 3], page_count=5)
    assert merged.verdict == "repair_pages"
    assert merged.bad_pages == [1, 3]
    assert "multicolumn" in merged.notes


def test_merge_ignores_oob_and_full_vision() -> None:
    base = QualityDecision(
        verdict="full_vision",
        bad_pages=[0],
        source="heuristic",
        notes="scan",
    )
    merged = merge_multicolumn_decision(base, [0, 99, 2], page_count=3)
    assert merged.verdict == "full_vision"
    assert 99 not in merged.bad_pages
    assert 2 in merged.bad_pages


def test_design_doc() -> None:
    root = Path(__file__).resolve().parents[1]
    design = (root / "docs" / "design" / "31-reading-order.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.32" in design
    assert "rich-v6" in design
