"""design/472 — the bundled web Hangul font holds every syllable the app writes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "mobile" / "assets" / "fonts"
HANGUL = re.compile(r"[\uac00-\ud7a3]")


def _cmap(name: str) -> set[int]:
    ttlib = pytest.importorskip("fontTools.ttLib")
    font = ttlib.TTFont(str(FONTS / name))
    return set(font.getBestCmap())


def test_design_472_ui_syllables_are_in_the_font() -> None:
    used: set[int] = set()
    for p in (ROOT / "mobile" / "lib").rglob("*.dart"):
        used.update(ord(c) for c in HANGUL.findall(p.read_text(encoding="utf-8")))
    assert ord("묻") in used
    for name in ("NotoSansKR-Regular.ttf", "NotoSansKR-Bold.ttf"):
        missing = sorted(chr(c) for c in used - _cmap(name))
        assert not missing, (name, "".join(missing), "run scripts/make_web_hangul_font.py")


def test_design_472_font_is_declared_and_licensed() -> None:
    pubspec = (ROOT / "mobile" / "pubspec.yaml").read_text(encoding="utf-8")
    assert "family: NotoSansKR" in pubspec
    assert "assets/fonts/NotoSansKR-Regular.ttf" in pubspec
    assert "assets/fonts/NotoSansKR-Bold.ttf" in pubspec
    assert (FONTS / "OFL-NotoSansKR.txt").is_file()
    app = (ROOT / "mobile" / "lib" / "app.dart").read_text(encoding="utf-8")
    assert app.count("fontFamilyFallback: kWebHangulFallback") == 2
