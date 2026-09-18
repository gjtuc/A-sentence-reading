"""design/288 — Main+SI index/pairing evidence densify (observability only)."""

from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_verdict import compute_pair_index_verdicts

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/288-main-si-index-pairing-evidence.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
DISK = ROOT / "mobile/lib/services/paper_disk_store.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
CACHE = ROOT / "src/sentence_reading/cache/paper_cache.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"
VERDICT = ROOT / "src/sentence_reading/llm/evidence_verdict.py"

VERSION = "0.3.283"
KINDS = (
    "library_index_upsert",
    "library_index_race",
    "library_publish_no_merge",
    "pairing_skip_multi",
    "figure_extract_done",
    "title_pipeline_empty",
)


def test_design_288_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert VERSION in text
    for k in KINDS:
        assert k in text
    assert "harmonize_poll_dropped_local" in text
    assert "index_upsert_lost_id" in text


def test_versions_288() -> None:
    # Ship pin lives in the design chip; later chips may bump app/pubspec/config.
    assert VERSION in DESIGN.read_text(encoding="utf-8")
    assert "288-main-si-index-pairing-evidence.md" in README.read_text(
        encoding="utf-8"
    )
    assert "0.3." in APP.read_text(encoding="utf-8")
    assert "0.3." in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3." in CONFIG.read_text(encoding="utf-8")


def test_kinds_mirrored_288() -> None:
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ALLOWED_KINDS
        assert k in FROZEN_KINDS
        assert f'"{k}"' in py or f"'{k}'" in py
        assert f"'{k}'" in dart


def test_emit_markers_288() -> None:
    floor = FLOOR.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    cache = CACHE.read_text(encoding="utf-8")
    ctrl = CTRL.read_text(encoding="utf-8")
    disk = DISK.read_text(encoding="utf-8")
    assert "title_pipeline_empty" in floor
    assert "library_index_upsert" in floor
    assert "figure_extract_done" in floor
    assert "title_pipeline_empty" in app
    assert "figure_extract_done" in app
    assert "role_empty" in app
    assert "doc_role" in cache and "supplementary" in cache
    assert "library_publish_no_merge" in ctrl
    assert "pairing_skip_multi" in ctrl
    assert "harmonize_poll" in ctrl
    assert "library_index_upsert" in disk
    assert "library_index_race" in disk
    assert "_indexWriteGen" in disk
    assert "compute_pair_index_verdicts" in VERDICT.read_text(encoding="utf-8")


def test_pair_index_verdicts_synthetic() -> None:
    events = [
        {
            "kind": "library_publish_no_merge",
            "ok": False,
            "details": {"missing_local_with_session_n": 1},
        },
        {
            "kind": "pairing_skip_multi",
            "ok": False,
            "details": {"skip_multi_main_n": 2},
        },
        {
            "kind": "open_ko_summary",
            "ok": True,
            "details": {"role_empty": 1, "doc_role": "empty"},
        },
        {
            "kind": "figure_extract_done",
            "ok": True,
            "details": {"supplementary": 1, "empty": 1, "fig_n": 0},
        },
        {
            "kind": "library_index_race",
            "ok": False,
            "code": "index_upsert_lost_id",
            "details": {},
        },
    ]
    got = compute_pair_index_verdicts(events)
    assert "harmonize_poll_dropped_local" in got
    assert "skip_multi_main_blocks_pair" in got
    assert "open_without_doc_role" in got
    assert "si_figure_zero_after_extract" in got
    assert "index_upsert_lost_id" in got


def test_pair_index_verdicts_from_pass_skip_main() -> None:
    events = [
        {
            "kind": "library_pairing_pass",
            "ok": True,
            "details": {"skip_multi_main_n": 1, "skip_multi_si_n": 0},
        },
    ]
    assert "skip_multi_main_blocks_pair" in compute_pair_index_verdicts(events)
