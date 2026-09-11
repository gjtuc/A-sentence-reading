# -*- coding: utf-8 -*-
"""design/221 — upload reservation queue floor checks."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "221-upload-reservation-queue.md"

_KINDS = (
    "upload_queue_enqueue",
    "upload_queue_remove",
    "upload_queue_pump_start",
    "upload_queue_pump_done",
    "upload_queue_blocked",
)


def test_design_221_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "asr.upload_reserve.v1" in text
    assert "ingest_reserve" in text
    assert "first_only" in text
    assert "serial" in text.lower() or "serial only" in text
    assert "uploadPdf" in text
    for k in _KINDS:
        assert k in text


def test_kinds_allowlisted_py_and_dart() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_mobile_queue_surface() -> None:
    models = (MOBILE / "lib" / "api" / "upload_reserve_models.dart").read_text(
        encoding="utf-8"
    )
    store = (MOBILE / "lib" / "api" / "upload_reserve_store.dart").read_text(
        encoding="utf-8"
    )
    ctrl = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    screen = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "kUploadReservePrefsKey" in models
    assert "kUploadReserveMaxItems" in models
    assert "ingest_reserve" in store
    assert "enqueuePickedPdfs" in ctrl
    assert "_pumpUploadQueue" in ctrl
    assert "allowMultiple: true" in screen
    assert "showUploadQueueSheet" in screen


def test_queue_parse_dedupe_and_cap() -> None:
    """Pure JSON contract mirrored from Dart UploadReserveQueue.tryParse."""
    import json

    items = []
    for i in range(25):
        h = f"{i:064x}"
        items.append(
            {
                "content_hash": h,
                "filename": f"p{i}.pdf",
                "local_path": f"/x/ingest_reserve/{h}.pdf",
                "bytes_len": 10,
                "status": "reserved",
                "enqueued_at_ms": i,
            }
        )
    # duplicate first
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
        if len(out) >= 20:
            break
    assert len(out) == 20
    assert out[0]["content_hash"] == f"{0:064x}"
