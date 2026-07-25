"""Signalsmith vendor + AsrStretch clamp/API 계약 검증 (브라우저 없이)."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "sentence_reading" / "static"
VENDOR_JS = STATIC / "vendor" / "signalsmith-stretch" / "SignalsmithStretch.js"
STRETCH_JS = STATIC / "tts_stretch.js"
INDEX_HTML = STATIC / "index.html"


def _clamp_rate_py(rate: object) -> float:
    """tts_stretch.js clampRate 와 동일 규칙 (경계값 미러)."""
    try:
        r = float(rate)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    if not (r > 0) or r != r or r == float("inf") or r == float("-inf"):
        return 1.0
    if r < 0.5:
        return 0.5
    if r > 2.2:
        return 2.2
    return r


def test_vendor_signalsmith_present() -> None:
    assert VENDOR_JS.is_file(), f"missing {VENDOR_JS}"
    assert VENDOR_JS.stat().st_size > 50_000
    text = VENDOR_JS.read_text(encoding="utf-8", errors="replace")
    assert "signalsmith-stretch" in text
    assert "AudioWorklet" in text


def test_index_loads_signalsmith_before_stretch() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    i_ss = html.find("vendor/signalsmith-stretch/SignalsmithStretch.js")
    i_st = html.find("tts_stretch.js")
    assert i_ss > 0 and i_st > i_ss


def test_asr_stretch_api_surface() -> None:
    src = STRETCH_JS.read_text(encoding="utf-8")
    for needle in (
        "clampRate",
        "playViaSignalsmith",
        "formantCompensation",
        "preservesPitch",
        "getEngine",
        "RATE_MIN",
        "RATE_MAX",
    ):
        assert needle in src, needle
    assert "global.AsrStretch" in src or "AsrStretch =" in src


def test_clamp_rate_edge_cases() -> None:
    assert _clamp_rate_py(1) == 1.0
    assert _clamp_rate_py(1.3) == 1.3
    assert _clamp_rate_py(0) == 1.0
    assert _clamp_rate_py(-3) == 1.0
    assert _clamp_rate_py("nope") == 1.0
    assert _clamp_rate_py(None) == 1.0
    assert _clamp_rate_py(float("nan")) == 1.0
    assert _clamp_rate_py(float("inf")) == 1.0
    assert _clamp_rate_py(0.1) == 0.5
    assert _clamp_rate_py(9.9) == 2.2


def test_js_clamp_literals_match_python() -> None:
    src = STRETCH_JS.read_text(encoding="utf-8")
    assert re.search(r"RATE_MIN\s*=\s*0\.5", src)
    assert re.search(r"RATE_MAX\s*=\s*2\.2", src)


if __name__ == "__main__":
    test_vendor_signalsmith_present()
    test_index_loads_signalsmith_before_stretch()
    test_asr_stretch_api_surface()
    test_clamp_rate_edge_cases()
    test_js_clamp_literals_match_python()
    print("ok: test_tts_stretch")
