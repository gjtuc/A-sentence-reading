"""design/139 — Fig. ref chip formalization (app + web · kill switch)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
PUB = ROOT / "mobile" / "pubspec.yaml"
DESIGN = ROOT / "docs" / "design" / "139-fig-ref-chip-formal.md"


def test_status_version_and_flags() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.70"
    assert st["fig_ref_hints"] is True
    assert st["fig_ref_chip_formal"] is True
    assert st["mobile_fig_ref_chip_formal"] is True


def test_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("ASR_FIG_REF_HINTS", "0")
    # WHY: status helpers read env at call time — recreate client after env.
    st = TestClient(app).get("/api/status").json()
    assert st["fig_ref_hints"] is False
    assert st["fig_ref_chip_formal"] is False
    monkeypatch.delenv("ASR_FIG_REF_HINTS", raising=False)


def test_wiring_app_web_design() -> None:
    assert DESIGN.is_file()
    # Chip shipped at 0.3.57; pubspec follows current app pin.
    assert "0.3.57" in DESIGN.read_text(encoding="utf-8")
    assert "0.3.70" in PUB.read_text(encoding="utf-8")
    reader = READER.read_text(encoding="utf-8")
    assert "design/139" in reader
    assert "OutlinedButton" in reader
    js = APP_JS.read_text(encoding="utf-8")
    assert "figRefHintsEnabled" in js
    assert "fig_ref_hints !== false" in js
    assert "textContent" in js  # XSS: no innerHTML for chip labels


def test_unmatched_ref_no_hint() -> None:
    from sentence_reading.fig_refs import hints_for_sentence
    from sentence_reading.models import Figure

    figs = [Figure(id="a", image_src="x", caption="Fig. 1 — only")]
    assert hints_for_sentence("see Fig. 99 nowhere", figs) == []
    # EDGE: empty / nonsense must not invent a chip.
    assert hints_for_sentence("", figs) == []
    assert hints_for_sentence(None, figs) == []
    assert hints_for_sentence("no figures here", figs) == []


def test_reader_uses_outlined_not_inline_textbutton() -> None:
    reader = READER.read_text(encoding="utf-8")
    # Isolate _figRefChipRow body.
    start = reader.index("List<Widget> _figRefChipRow")
    end = reader.index("\n}", start)
    body = reader[start:end]
    assert "OutlinedButton" in body
    assert "TextButton" not in body
    assert "secondaryContainer" not in body
