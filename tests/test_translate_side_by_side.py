"""번역 EN|KO 좌우 동형 (0.3.3 · design/39)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]


def test_status_side_by_side() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.31"
    assert st["translate_side_by_side"] is True


def test_design_39_contract() -> None:
    design = (ROOT / "docs" / "design" / "39-translate-side-by-side.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.47" in design
    assert "is-split" in design
    assert "전체화면" in design or "축소" in design
    assert "Live Enable" in design or "IPS" in design


def test_dom_and_css_side_by_side() -> None:
    html = (ROOT / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="sentenceBilingual"' in html
    assert 'id="sentenceKoFrame"' in html
    assert "design/39" in html
    css = (ROOT / "src" / "sentence_reading" / "static" / "styles.css").read_text(
        encoding="utf-8"
    )
    assert ".sentence-bilingual.is-split" in css
    assert "design/39" in css
    # KO 타이포가 EN 과 동일 토큰
    assert "font-size: var(--sentence-size)" in css
    ko_block = css.split(".sentence-ko {", 1)[1].split("}", 1)[0]
    assert "var(--fg)" in ko_block
    assert "text-align: center" in ko_block
    assert "0.78" not in ko_block  # 예전 축소 배율 제거
    assert "fg-muted" not in ko_block
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "setBilingualSplit" in js
    assert "design/39" in js
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.31" in served
    assert "styles.css?v=0.3.31" in served
