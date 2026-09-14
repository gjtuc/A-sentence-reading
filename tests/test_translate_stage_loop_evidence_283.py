"""design/283 — translate/ingest stage loop & regress evidence."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/283-translate-stage-loop-evidence.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
STAGE_DART = ROOT / "mobile/lib/state/ingest_stage_progress.dart"
GUARD = ROOT / "src/sentence_reading/llm/translate_progress_guard.py"
TRANSLATE = ROOT / "src/sentence_reading/llm/translate_section.py"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"

KINDS = (
    "translate_section_enter",
    "translate_harmonize_start",
    "translate_harmonize_tick",
    "translate_harmonize_end",
    "translate_progress_regress",
    "translate_stage_loop",
    "ingest_progress_regress",
    "ingest_stage_loop",
    "ingest_stage_tick",
    "ingest_auto_resume_loop",
)


def test_design_283_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.278" in text
    for k in KINDS:
        assert k in text


def test_versions_283() -> None:
    app = APP.read_text(encoding="utf-8")
    assert 'version="0.3.278"' in app
    assert '"version": "0.3.278"' in app
    assert "0.3.278" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.278" in CONFIG.read_text(encoding="utf-8")
    assert "283-translate-stage-loop-evidence.md" in README.read_text(
        encoding="utf-8"
    )


def test_kinds_mirrored_283() -> None:
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS

    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ALLOWED_KINDS
        assert k in FROZEN_KINDS
        assert f'"{k}"' in py or f"'{k}'" in py
        assert f"'{k}'" in dart
        assert f'"{k}"' in floor


def test_markers_283() -> None:
    assert "_emit_section_enter_pass" in TRANSLATE.read_text(encoding="utf-8")
    assert "_emit_harmonize_pass_tick" in TRANSLATE.read_text(encoding="utf-8")
    assert "TranslatePassTracker" in GUARD.read_text(encoding="utf-8")
    assert "parseIngestStageFraction" in CTRL.read_text(encoding="utf-8")
    assert "ingest_auto_resume_loop" in CTRL.read_text(encoding="utf-8")
    assert "IngestStagePassTracker" in STAGE_DART.read_text(encoding="utf-8")


def test_tracker_section_loop_and_regress() -> None:
    from sentence_reading.llm.translate_progress_guard import TranslatePassTracker

    t = TranslatePassTracker()
    d1 = t.note_section_enter(job_id="j1", section="introduction", in_n=135)
    assert d1["pass_n"] == 1 and d1["loop"] == 0
    d2 = t.note_section_enter(job_id="j1", section="introduction", in_n=135)
    assert d2["pass_n"] == 2 and d2["loop"] == 1

    h = t.note_harmonize_start(job_id="j1", section="introduction", in_n=135)
    assert h["pass_n"] == 1
    tick1, reg1 = t.note_harmonize_tick(
        job_id="j1", section="introduction", out_n=120, in_n=135, remaining=15
    )
    assert not reg1
    tick2, reg2 = t.note_harmonize_tick(
        job_id="j1", section="introduction", out_n=1, in_n=135, remaining=134
    )
    assert reg2
    assert tick2["regress"] == 1
    assert tick2["prev_out_n"] == 120

    # Residual arm must not trip main harmonize loop.
    r = t.note_harmonize_start(
        job_id="j1", section="introduction", in_n=10, residual=True
    )
    assert r["phase"] == "harmonize_residual"
    assert r["loop"] == 0
