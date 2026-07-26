"""보관 목록 UI 계약 (정적)."""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "sentence_reading" / "static"


def test_library_markup() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="libraryBtn"' in html
    assert 'id="libraryDialog"' in html
    assert 'id="libraryList"' in html
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".library-list" in css
    assert ".library-item-delete" in css
    assert ".library-item-row" in css


def test_library_js_wiring() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "openLibraryDialog" in app
    assert "openCachedPaper" in app
    assert "refreshLibraryList" in app
    assert "deleteLibraryPaper" in app
    assert "library-item-delete" in app
    assert "p.cacheId && paper.cacheId" in app


if __name__ == "__main__":
    test_library_markup()
    test_library_js_wiring()
    print("ok: test_paper_library")
