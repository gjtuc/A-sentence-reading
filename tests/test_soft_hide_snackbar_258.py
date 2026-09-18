"""design/258 — soft-hide countdown snackbar + abandon enrich on hide."""
from __future__ import annotations

from pathlib import Path
from asr_versions import app_version

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/258-soft-hide-snackbar-abandon-enrich.md"
LIB_SCREEN = ROOT / "mobile/lib/screens/library_screen.dart"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_258_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.258" in text
    assert "live countdown" in text or "카운트다운" in text or "{secs}초" in text


def test_versions_258() -> None:
    # design/258 shipped at 0.3.258; later chips may bump further.
    app = APP.read_text(encoding="utf-8")
    assert f'version="{app_version()}"' in app
    assert "0.3." in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3." in CONFIG.read_text(encoding="utf-8")


def test_snackbar_countdown() -> None:
    src = LIB_SCREEN.read_text(encoding="utf-8")
    assert "_SoftHideCountdownContent" in src
    assert r"$_secsLeft초 후 영구 삭제됩니다." in src
    assert "purgeDueSoftDeletes" in src
    assert "1분 후 영구 삭제됩니다." not in src


def test_soft_hide_abandons_enrich() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "_abandonBackgroundWorkForSoftHide" in ctrl
    assert "paper_soft_hide_abandon_work" in ctrl
    assert "soft_hide_abort" in ctrl
    assert "_isSoftHideAbandoned" in ctrl
    assert "purgeAtMs" in ctrl
