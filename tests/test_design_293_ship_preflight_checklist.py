"""design/293 — ship_release preflight checklist."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/293-ship-preflight-checklist.md"
README = ROOT / "docs/design/README.md"
SHIP = ROOT / "scripts/ship_release.sh"


def test_design_293_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "preflight" in text.lower()
    assert "tracked" in text.lower()


def test_ship_release_preflight_293() -> None:
    assert "293-ship-preflight-checklist.md" in README.read_text(encoding="utf-8")
    ship = SHIP.read_text(encoding="utf-8")
    assert "design/293" in ship
    assert "tracked working tree dirty" in ship or "porcelain --untracked-files=no" in ship
    assert "ASR_SHIP_ALLOW_UNPUSHED" in ship
    assert "version mismatch across app/pubspec/config" in ship
    assert "preflight checklist" in ship
