# -*- coding: utf-8 -*-
"""Rich display + TTS polish contract (0.3.4 · design/88; lexicon 0.3.5 · design/90)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.tts_speak import spoken_text_for_tts

ROOT = Path(__file__).resolve().parents[1]


def test_status_version_0_3_12() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.49"


def test_design_88_exists() -> None:
    p = ROOT / "docs" / "design" / "88-rich-display-tts-polish.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.4" in text
    assert "TTS" in text


def test_design_90_unit_lexicon() -> None:
    p = ROOT / "docs" / "design" / "90-tts-unit-lexicon.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.5" in text
    assert "watt hour" in text.lower() or "Wh" in text


def test_design_92_figure_caption_order() -> None:
    p = ROOT / "docs" / "design" / "92-figure-caption-order.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.6" in text
    assert "rich-v12" in text
    assert "Graphical abstract" in text or "caption" in text.lower()


def test_design_93_remove_live_enable_footer() -> None:
    p = ROOT / "docs" / "design" / "93-remove-live-enable-footer.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.7" in text
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "Live Enable" not in reader
    shadow = (
        ROOT / "mobile" / "lib" / "screens" / "shadowing_practice_screen.dart"
    ).read_text(encoding="utf-8")
    # no user-facing widget string (doc comments may still mention)
    assert "'Live Enable" not in shadow
    assert '"Live Enable' not in shadow


def test_design_94_figure_zoom_fill_frame() -> None:
    p = ROOT / "docs" / "design" / "94-figure-zoom-fill-frame.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.8" in text
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "_ZoomableFigureFrame" in reader
    assert "LayoutBuilder" in reader


def test_design_95_reader_swipe_nav() -> None:
    p = ROOT / "docs" / "design" / "95-reader-swipe-nav.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.9" in text
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "_SwipePager" in reader
    # design/116 — pan always on; 1× swipe from pan-end (not parent HorizontalDrag).
    assert "panEnabled: true" in reader or "panEnabled:true" in reader.replace(" ", "")
    assert "design/116" in reader


def test_design_96_tts_settings_tab() -> None:
    p = ROOT / "docs" / "design" / "96-tts-settings-tab.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.10" in text
    settings = (
        ROOT / "mobile" / "lib" / "screens" / "settings_screen.dart"
    ).read_text(encoding="utf-8")
    assert "required this.tts" in settings or "required this.tts," in settings
    assert "kTtsRateMin" in settings
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "'speed'" not in reader and '"speed"' not in reader
    assert "연습" in reader


def test_design_97_reader_panel_expand() -> None:
    p = ROOT / "docs" / "design" / "97-reader-panel-expand.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.11" in text
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "_ReaderLayoutMode" in reader
    assert "onDoubleTapExpand" in reader
    assert "sentenceOnly" in reader and "figureOnly" in reader


def test_design_98_reader_split_drag() -> None:
    p = ROOT / "docs" / "design" / "98-reader-split-drag.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.12" in text
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "_SplitHandle" in reader
    assert "_onSplitDragUpdate" in reader
    assert "_kDefaultFraction" in reader


def test_design_100_reader_chrome_toggle() -> None:
    p = ROOT / "docs" / "design" / "100-reader-chrome-toggle.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.14" in text
    reader = (
        ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
    ).read_text(encoding="utf-8")
    assert "_chromeVisible" in reader
    assert "_toggleChrome" in reader
    assert "showChrome" in reader
    assert "onToggleChrome" in reader


def test_flutter_rich_sentence_module() -> None:
    dart = ROOT / "mobile" / "lib" / "api" / "rich_sentence.dart"
    assert dart.is_file()
    body = dart.read_text(encoding="utf-8")
    assert "buildRichSpans" in body
    assert "sub" in body


def test_web_client_sanitize_present() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "sanitizeSentenceHtmlClient" in js
    assert "setSentenceKoDisplay" in js


def test_tts_cm_inverse_contract() -> None:
    assert "per centimeter" in spoken_text_for_tts("1650 cm<sup>−1</sup>").lower()


def test_tts_wh_per_liter_not_tungsten() -> None:
    out = spoken_text_for_tts("2800 W h L<sup>-1</sup>").lower()
    assert "watt hour per liter" in out
    assert "tungsten" not in out
