# -*- coding: utf-8 -*-
"""design/224 — library density UX wiring (soft-delete · nav · TTS UI)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "224-library-density-ux.md"


def test_design_224_locked_doc() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.223" in text
    assert "soft-hide" in text.lower() or "Soft-hide" in text
    assert "random_auto" in text
    assert "nav_surface" in text


def test_soft_delete_store_wiring() -> None:
    models = (MOBILE / "lib" / "api" / "library_soft_delete_models.dart").read_text(
        encoding="utf-8"
    )
    store = (MOBILE / "lib" / "api" / "library_soft_delete_store.dart").read_text(
        encoding="utf-8"
    )
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    screen = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "asr.lib_soft_del.v1.u." in models
    assert "kSoftDeleteGrace" in models
    assert "PrefsLibrarySoftDeleteStore" in store
    assert "softHidePapers" in ctrl
    assert "undoSoftHide" in ctrl
    assert "purgeDueSoftDeletes" in ctrl
    assert "_publishPapers" in ctrl
    assert "softHidePapers" in screen
    assert "실행 취소" in screen


def test_shell_density_nav() -> None:
    shell = (MOBILE / "lib" / "screens" / "home_shell.dart").read_text(encoding="utf-8")
    assert "nav_surface" in shell
    assert "onOpenSettings" in shell
    assert "NavigationBar" not in shell
    assert "label: '읽기'" not in shell
    assert "_readerSurface" in shell
    assert "PopScope" in shell


def test_tts_ui_two_modes() -> None:
    models = (MOBILE / "lib" / "api" / "tts_models.dart").read_text(encoding="utf-8")
    settings = (MOBILE / "lib" / "screens" / "settings_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "kTtsModesUi" in models
    assert "normalizeTtsModeUi" in models
    assert "사용자 선택" in models
    assert "kTtsModesUiOrdered" in settings
    assert "kTtsModeRandomHard" not in settings
    assert "kTtsModeRandomVeryHard" not in settings
