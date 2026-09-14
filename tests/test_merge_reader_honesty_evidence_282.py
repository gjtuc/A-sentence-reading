"""design/282 — merge/reader honesty evidence densify."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/282-merge-reader-honesty-evidence.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"

KINDS = (
    "reader_open_honesty",
    "paper_merge_postcheck",
    "paper_notify_open",
    "documents_mirror_done",
)


def test_design_282_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.277" in text
    assert "mismatch_merged" in text
    assert "paper_merge_postcheck" in text
    for k in KINDS:
        assert k in text


def test_versions_282() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.277"' in app
    assert '"version": "0.3.277"' in app
    assert "0.3.277" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.277" in CONFIG.read_text(encoding="utf-8")
    assert "282-merge-reader-honesty-evidence.md" in README.read_text(
        encoding="utf-8"
    )


def test_kinds_mirrored_282() -> None:
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS

    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ALLOWED_KINDS
        assert f'"{k}"' in py or f"'{k}'" in py
        assert f"'{k}'" in dart
        assert k in FROZEN_KINDS


def test_emit_markers_282() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ctrl
        assert k in floor
    assert "_emitReaderOpenHonesty" in ctrl
    assert "_emitMergePostcheck" in ctrl
    assert "_mirrorPaperWithEvidence" in ctrl
    assert "mismatch_ui_disk" in ctrl
    assert "si_id_empty" in ctrl
    assert "supp_section_n" in ctrl
