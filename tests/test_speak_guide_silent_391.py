"""design/391 - the speak-phase guide is silent on earphones too."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "mobile" / "lib" / "screens" / "shadowing_practice_screen.dart"


def _src() -> str:
    return SCREEN.read_text(encoding="utf-8")


def test_speak_guide_volume_is_zero() -> None:
    m = re.search(r"_kSpeakTtsVolume\s*=\s*([0-9.]+)\s*;", _src())
    assert m is not None
    assert float(m.group(1)) == 0.0


def test_speak_volume_does_not_depend_on_headset() -> None:
    assert "hasHeadset" not in _src()


def test_listen_stays_full_volume() -> None:
    m = re.search(r"_kFullTtsVolume\s*=\s*([0-9.]+)\s*;", _src())
    assert m is not None
    assert float(m.group(1)) == 1.0


def test_doc_and_readme_row() -> None:
    doc = ROOT / "docs" / "design" / "391-speak-guide-silent-on-earphones.md"
    assert doc.is_file()
    readme = (ROOT / "docs" / "design" / "README.md").read_text(encoding="utf-8")
    assert "391-speak-guide-silent-on-earphones.md" in readme
