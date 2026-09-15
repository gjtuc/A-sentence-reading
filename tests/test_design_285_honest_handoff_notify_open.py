"""design/285 — honest handoff notify + openByCacheId resolve."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/285-honest-handoff-notify-open.md"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
README = ROOT / "docs/design/README.md"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"

VERSION = "0.3.281"


def test_design_285_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert VERSION in text
    assert "N1" in text
    assert "N2" in text
    assert "showCompleted" in text
    assert "same_hash" in text
    assert "disk_session" in text


def test_versions_285() -> None:
    assert VERSION in APP.read_text(encoding="utf-8")
    assert VERSION in PUBSPEC.read_text(encoding="utf-8")
    assert VERSION in CONFIG.read_text(encoding="utf-8")
    assert "285-honest-handoff-notify-open.md" in README.read_text(encoding="utf-8")


def test_emit_markers_285() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "design/285" in ctrl
    assert "기기로 옮기기에 실패했습니다" in ctrl
    assert "hit_mate" in ctrl
    assert "hit_same_hash" in ctrl
    assert "hit_disk" in ctrl
    assert "resolve = 'mate'" in ctrl or 'resolve = "mate"' in ctrl
    assert "same_hash" in ctrl
    assert "disk_session" in ctrl
    # Both upload complete paths gate on !handoffOk before showCompleted.
    assert ctrl.count("completed notify requires handoff success") >= 2
