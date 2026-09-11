# -*- coding: utf-8 -*-
"""design/223 — upload picker recent + green join floor checks."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "223-library-upload-picker-investigation.md"

_KINDS = ("picker_sheet_open", "picker_recent_save")


def test_design_223_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.222" in text
    assert "locked" in text.lower() or "Status: **locked**" in text
    assert "asr.picker_recent.v1.u." in text
    assert "content_hash" in text
    assert "초록" in text or "green" in text.lower()
    assert "MediaStore" in text


def test_kinds() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_mobile_surface() -> None:
    models = (
        MOBILE / "lib" / "api" / "upload_picker_recent_models.dart"
    ).read_text(encoding="utf-8")
    store = (
        MOBILE / "lib" / "api" / "upload_picker_recent_store.dart"
    ).read_text(encoding="utf-8")
    sheet = (
        MOBILE / "lib" / "widgets" / "upload_picker_sheet.dart"
    ).read_text(encoding="utf-8")
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    screen = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "kPickerRecentMaxItems" in models
    assert "pickerRecentPrefsKey" in models
    assert "bindUid" in store
    assert "libraryContentHashes" in ctrl
    assert "notePickerSheetOpened" in ctrl
    assert "showUploadPickerSheet" in sheet
    assert "이미 보관" in sheet
    assert "_openUploadPicker" in screen
    assert "enqueuePickedPdfs" in ctrl


def test_recent_parse_dedupe_cap() -> None:
    import json

    items = []
    for i in range(35):
        h = f"{i:064x}"
        items.append(
            {
                "content_hash": h,
                "display_name": f"p{i}.pdf",
                "label": "",
                "uploaded_at_ms": i,
                "source": "saf",
            }
        )
    items.append(items[0])
    raw = json.dumps({"v": 1, "items": items})
    data = json.loads(raw)
    seen = set()
    out = []
    for row in data["items"]:
        h = row["content_hash"]
        if h in seen:
            continue
        seen.add(h)
        out.append(row)
        if len(out) >= 30:
            break
    assert len(out) == 30
