"""되새김질 키보드 패리티 (0.2.64 · design/56)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "56-section-review-keys.md"


def test_status_section_review_keys() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.31"
    assert st["section_review_keys"] is True
    assert st["section_review_flow_edit"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_key_handler_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "design/56" in src
    assert "handleSectionReviewKeys" in src
    assert "focusSectionReviewSeg" in src
    assert "isFocusInSectionReviewEdit" in src
    assert "is-flow-focus" in src
    assert "flowSegIndex" in src
    # Esc: edit cancel before close
    assert "cancelSectionReviewFlowEdit" in src
    assert "handleSectionReviewKeys(ev)" in src
    css = CSS.read_text(encoding="utf-8")
    assert ".section-review-flow-seg.is-flow-focus" in css
    html = INDEX.read_text(encoding="utf-8")
    assert "←/→" in html or "흰 십자" in html or "구간" in html


def test_edge_and_index_invariant() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    start = src.find("function handleSectionReviewKeys")
    end = src.find("\n  function playNoteSentence", start)
    if end < 0:
        end = src.find("\n  function openNoteOverlay", start)
    assert start > 0 and end > start
    chunk = src[start:end]
    assert "sentenceIndex" not in chunk
    assert "figureIndex" not in chunk
    assert "advanceSentence" not in chunk
    assert "advanceFigure" not in chunk
    # empty segs → continue / sheet focus path
    assert "sectionReviewContinue" in chunk
    # arrow clamp
    assert "if (next < 0) next = 0" in chunk


def test_design_and_assets() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.64" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.31" in served
    assert "styles.css?v=0.3.31" in served
