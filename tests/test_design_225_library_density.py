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
    """design/225 hide path survived design/308's custom hold+drag.

    The magnet pad / SliverReorderableList drop target is gone; hide is the
    hold-menu delete and the select-mode trash icon. Both still call the
    same undo helper and must not persist order.
    """
    lib = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    hold = (MOBILE / "lib" / "widgets" / "library_card_hold.dart").read_text(
        encoding="utf-8"
    )
    assert "_softHideWithUndo" in lib
    assert "Icons.delete_outline" in lib
    assert "숨기기" in lib
    assert "softHidePapers" in lib
    assert "LibraryCardHold" in lib
    assert "design/308" in hold
    hide_fn = lib.split("Future<void> _softHideWithUndo")[1].split(
        "Future<void> _confirmDelete"
    )[0]
    assert "reorderPapers" not in hide_fn
    assert "reorderPaperBlock" not in hide_fn
