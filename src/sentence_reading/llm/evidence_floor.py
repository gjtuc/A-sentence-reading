"""design/169g — frozen evidence kinds/markers; block sensor regression on deploy."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Live must not lose sensors introduced by 169c/d/e/g/h/i/j/k (floor through pull verdicts).
EVIDENCE_FLOOR_VERSION = "0.3.157"

FROZEN_KINDS: frozenset[str] = frozenset(
    {
        "translate_phase_enter",
        "translate_phase_exit",
        "translate_item_done",
        "translate_call_start",
        "translate_call_done",
        "translate_call_slow",
        "translate_call_fail",
        "translate_save_ko",
        "open_ko_summary",
        "translate_poll_start",
        "translate_poll_ko",
        "handoff",
        "progress_view",
        "checkpoint",
        "artifact_observe",
        "artifact_transfer",
        "artifact_derive",
        "artifact_invalidate",
        "reanalyze_pref_snapshot",
        "stall_fired",
        "figure_preserve_miss",
        "figure_meta_write",
        "figure_meta_regress",
        "figure_preserve_skip",
        "ingest_integrity_violation",
        "library_refresh",
        "paper_delete",
        "figure_window_req",
        "figure_window_res",
        "server_job_terminal_error",
        "download_cache_fail",
        "papers_upload_fail",
        "library_list_miss",
        "papers_supersede_gc",
        "papers_delete_residual",
        "papers_gcs_orphan_sample",
        "reclaim_seed",
        "lease_heartbeat",
        "sweep_decision",
        "reclaim_attempt",
        "figure_hydrate_start",
        "figure_hydrate_progress",
        "figure_hydrate_done",
        "figure_hydrate_partial",
        "figure_hydrate_abort",
        "harmonize_residual_start",
        "harmonize_residual_progress",
        "harmonize_residual_done",
        "harmonize_residual_partial",
        "harmonize_residual_abort",
        # design/169p
        "shadowing_gate",
        "shadowing_ensure_start",
        "shadowing_ensure_done",
        "shadowing_boot_start",
        "shadowing_boot_done",
        "shadowing_build_round",
        "shadowing_loop_event",
        "shadowing_chunks_get",
        "shadowing_chunks_build_start",
        "shadowing_chunks_build_done",
        "shadowing_gemini_call_start",
        "shadowing_gemini_call_done",
        "shadowing_ingest_stage",
    }
)

# Relative to repo root. Each marker must appear in file text.
FROZEN_EMIT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "src/sentence_reading/llm/progressive_writer.py",
        (
            "on_item_enqueue",
            "writer_drop",
            "writer_done",
            "writer_flush",
            "ProgressiveWriter",
            "put_nowait",
        ),
    ),
    (
        "src/sentence_reading/llm/translate_section.py",
        (
            "translate_call_start",
            "translate_call_done",
            "_google_batch_timed",
            "_gemini_timed",
            '_emit_translate_call("translate_call_start", call_kind=call_kind)',
            "_emit_handoff",
            "_emit_checkpoint",
            "_bind_evidence_ctx",
            "harmonize_pool_start",
            "next_section_armed",
            'from_stage="google_batch"',
            "trace_id=trace_id",
            '_EVIDENCE_CTX.trace_id',
            # design/169j — lock not held across on_item
            "on_item(kind, index, ko, stage)",
            # design/169o
            "run_harmonize",
            "harmonize_session_residual",
            "count_harmonize_targets",
        ),
    ),
    (
        "src/sentence_reading/llm/track_verdict.py",
        (
            "JobTimeline",
            "compute_verdicts",
            "zombie_worker",
            "accept_169j_title",
        ),
    ),
    (
        "scripts/track_translate.py",
        (
            "track_verdict",
            "accept_169j_title",
        ),
    ),
    (
        "src/sentence_reading/llm/artifact_ids.py",
        (
            "emit_artifact_transfer",
            "emit_artifact_observe",
            "emit_artifact_derive",
            "emit_artifact_invalidate",
            "hash16",
            "locator_local_session",
            "locator_gcs_session",
        ),
    ),
    (
        "src/sentence_reading/cache/paper_cache.py",
        (
            "artifact_gen",
            "emit_artifact_derive",
            "local_write_session",
            "figure_meta_write",
            "_emit_figure_meta_boundary",
        ),
    ),
    (
        "src/sentence_reading/llm/ingest_integrity.py",
        (
            "check_figure_file_rel",
            "ingest_integrity_violation",
        ),
    ),
    (
        "src/sentence_reading/llm/papers_gcs.py",
        (
            "gcs_upload_session",
            "gcs_download_session",
            "emit_artifact_invalidate",
            "wipe_paper_prefix",
            "gc_superseded_paper",
            "upload_remote_index_cas",
            "papers_supersede_gc",
            "papers_delete_residual",
        ),
    ),
    (
        "src/sentence_reading/llm/translate_google.py",
        ("translate_call_start", "google_chunk", "translate_call_done"),
    ),
    (
        "src/sentence_reading/api/app.py",
        (
            "translate_phase_enter",
            "translate_phase_exit",
            "open_ko_summary",
            "progress_view",
            'view_side": "server"',
            "emit_handoff",
            'from_stage="client_upload"',
            'from_stage="translate_phase_exit"',
            'from_stage="reading_ready"',
            'from_stage="client_delete"',
            "_emit_paper_delete_evidence",
            "_job_trace_id",
            "trace_id=job_trace",
            "_evidence_rotate_loop",
            "evidence_retention_days",
            "ProgressiveWriter",
            "prog_writer.flush",
            "enqueue_publish",
            "patch_gen",
            "job_terminal",
            "session_patch_ko",
            "_translate_patch_seq",
            "IngestCancelled",
            "lease_heartbeat",
            "sweep_decision",
            "mem_lease_age_sec",
            "gcs_lease_age_sec",
            # design/169o
            "_run_harmonize_residual",
            "harmonize_pending",
            "harmonize_residual_start",
            # design/169p
            "shadowing_chunks_get",
            "shadowing_chunks_build_start",
            "shadowing_chunks_build_done",
            "shadowing_ingest_stage",
        ),
    ),
    (
        "src/sentence_reading/llm/shadowing_chunks.py",
        (
            "shadowing_gemini_call_start",
            "shadowing_gemini_call_done",
            "call_kind",
        ),
    ),
    (
        "src/sentence_reading/llm/shadowing_verdict.py",
        (
            "ShadowingTimeline",
            "compute_shadowing_verdicts",
            "prep_ui_stuck",
            "accept_prep_ok",
        ),
    ),
    (
        "scripts/track_shadowing.py",
        (
            "shadowing_verdict",
            "compute_shadowing_verdicts",
        ),
    ),
    (
        "src/sentence_reading/llm/ingest_lease_obs.py",
        (
            "lease_age_sec",
            "mem_snapshot",
            "gcs_snapshot",
            "emit_dual",
            "cr_rev8",
        ),
    ),
    (
        "src/sentence_reading/llm/evidence_bus.py",
        ("emit_handoff", "new_handoff_id", "stage_token", "rotate_events", "filter_retained"),
    ),
    (
        "scripts/rotate_evidence.py",
        ("rotate_events", "--force"),
    ),
    (
        "src/sentence_reading/llm/evidence_kinds.py",
        tuple(sorted(FROZEN_KINDS)),
    ),
    (
        "mobile/lib/services/evidence_kinds.dart",
        tuple(sorted(FROZEN_KINDS)),
    ),
    (
        "mobile/lib/api/client.dart",
        ("progress_view", "_progressMsgHash", "view_side", "adoptJobTrace"),
    ),
    (
        "mobile/lib/services/evidence_bus.dart",
        ("recordHandoff", "newHandoffId", "adoptJobTrace"),
    ),
    (
        "mobile/lib/state/library_controller.dart",
        (
            "reanalyze_pref_snapshot",
            "translate_poll_start",
            "paper_delete",
            "recordHandoff",
            "client_upload",
            "client_open",
            "client_delete",
            "reconcileUploadNotify",
            "figure_hydrate_start",
            "enqueueFigureHydrate",
            "hydrate_bg",
            "harmonize_residual_start",
            "enqueueHarmonizeResidualPoll",
            # design/169p
            "shadowing_ensure_start",
            "shadowing_ensure_done",
            "shadowing_gate",
            "_shadowingWantProbe",
        ),
    ),
    (
        "mobile/lib/screens/shadowing_practice_screen.dart",
        (
            "shadowing_boot_start",
            "shadowing_boot_done",
            "shadowing_loop_event",
            "shadowing_gate",
        ),
    ),
)


def verify_evidence_floor(*, root: Path | None = None) -> list[str]:
    """Return error codes; empty list means OK."""
    base = root or ROOT
    errs: list[str] = []

    kinds_py = base / "src" / "sentence_reading" / "llm" / "evidence_kinds.py"
    kinds_dart = base / "mobile" / "lib" / "services" / "evidence_kinds.dart"
    if not kinds_py.is_file():
        return ["evidence_kinds_py_missing"]
    if not kinds_dart.is_file():
        return ["evidence_kinds_dart_missing"]

    py_text = kinds_py.read_text(encoding="utf-8")
    dart_text = kinds_dart.read_text(encoding="utf-8")
    for kind in sorted(FROZEN_KINDS):
        if f'"{kind}"' not in py_text and f"'{kind}'" not in py_text:
            errs.append(f"kind_missing_py:{kind}")
        if f"'{kind}'" not in dart_text and f'"{kind}"' not in dart_text:
            errs.append(f"kind_missing_dart:{kind}")

    for rel, markers in FROZEN_EMIT_MARKERS:
        path = base / rel
        if not path.is_file():
            errs.append(f"marker_file_missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errs.append(f"marker_missing:{rel}:{marker}")

    return errs
