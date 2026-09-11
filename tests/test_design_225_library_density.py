# -*- coding: utf-8 -*-
"""design/225 — library density follow-ups wiring."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "225-library-density-followups.md"


def test_design_225_locked() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.224" in text
    assert "225-U" in text
    assert "225-F" in text
    assert "onSoftHideOpened" in text or "224b" in text


def test_soft_hide_leaves_reader_wiring() -> None:
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    shell = (MOBILE / "lib" / "screens" / "home_shell.dart").read_text(
        encoding="utf-8"
    )
    assert "onSoftHideOpened" in ctrl
    assert "onSoftHideOpened" in shell
    assert "_goLibrary(recordLeft: false)" in shell


def test_upload_status_bar_shared() -> None:
    bar = (MOBILE / "lib" / "widgets" / "upload_status_bar.dart").read_text(
        encoding="utf-8"
    )
    lib = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    reader = (MOBILE / "lib" / "screens" / "reader_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "class UploadStatusBar" in bar
    assert "cancelUpload" in bar
    assert "UploadStatusBar" in lib
    assert "UploadStatusBar" in reader


def test_magnetic_trash_wiring() -> None:
    lib = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "_trashKey" in lib
    assert "_dragOverTrash" in lib
    assert "_softHideWithUndo" in lib
    assert "onReorderStart" in lib
    assert "_magnetPad" in lib
    assert "Listener(" in lib
