"""design/279 — mate/merge/pairing causal evidence + soft-hide allowlist fix."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/279-mate-merge-pair-causal-evidence.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
DISK = ROOT / "mobile/lib/services/paper_disk_store.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"

KINDS = (
    "paper_soft_hide",
    "paper_soft_undo",
    "paper_soft_hide_abandon_work",
    "library_pairing_pass",
    "paper_merge_start",
    "paper_merge_local_done",
    "paper_merge_done",
)


def test_design_279_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.272" in text
    assert "silently dropped" in text or "allowlist" in text
    for k in KINDS:
        assert k in text


def test_versions_279() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.272"' in app
    assert '"version": "0.3.272"' in app
    assert "0.3.272" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.272" in CONFIG.read_text(encoding="utf-8")
    assert "279-mate-merge-pair-causal-evidence.md" in README.read_text(
        encoding="utf-8"
    )


def test_kinds_mirrored_279() -> None:
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS

    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ALLOWED_KINDS
        assert f'"{k}"' in py or f"'{k}'" in py
        assert f"'{k}'" in dart
        assert k in FROZEN_KINDS


def test_emit_markers_279() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    disk = DISK.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    assert "library_pairing_pass" in ctrl
    assert "paper_merge_start" in ctrl
    assert "paper_merge_local_done" in ctrl
    assert "paper_merge_done" in ctrl
    assert "applyLocalPairingPassDetailed" in ctrl
    assert "LocalPairingPassStats" in disk
    assert "skip_multi_main_n" in ctrl
    assert "library_controller.dart" in floor
    assert "paper_merge_local_done" in floor
