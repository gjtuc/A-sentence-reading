"""되새김질 flow 콕 수정 (0.2.63 · design/55)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
NOTES = STATIC / "notes_revisions.js"
DESIGN = ROOT / "docs" / "design" / "55-section-review-flow-edit.md"


def test_status_flow_edit() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.21"
    assert st["section_review_flow_edit"] is True
    assert st["section_review_flow"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_flow_edit_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "design/55" in src
    assert "beginSectionReviewFlowEdit" in src
    assert "commitSectionReviewFlowEdit" in src
    assert "cancelSectionReviewFlowEdit" in src
    assert "section-review-flow-seg" in src
    assert "flowEntries" in src
    assert "commitNoteRevision" in src
    # 단일 join 박스 제거
    assert "flowParts.join" not in src
    css = CSS.read_text(encoding="utf-8")
    assert ".section-review-flow-seg" in css
    assert ".section-review-flow-edit" in css
    html = INDEX.read_text(encoding="utf-8")
    assert "Enter" in html or "수정" in html
    assert "이어" in html


def test_edge_guards_and_append_only() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "if (!seg || !entry || !entry.sid) return" in src
    notes = NOTES.read_text(encoding="utf-8")
    assert "appendTextRevision" in notes
    # close flushes edit
    assert "if (noteUi.flowEdit)" in src
    assert "commitSectionReviewFlowEdit({ reopen: false })" in src
    # must not assign sentenceIndex in edit helpers
    start = src.find("function beginSectionReviewFlowEdit")
    end = src.find("\n  async function onSectionReviewPlayVoiceSequence", start)
    assert start > 0 and end > start
    chunk = src[start:end]
    assert "sentenceIndex" not in chunk


def test_design_and_assets() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.63" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.21" in served
    assert "styles.css?v=0.3.21" in served
