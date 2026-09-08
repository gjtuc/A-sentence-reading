"""design/169g — frozen evidence kinds/markers; block sensor regression on deploy."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Live must not lose sensors introduced by 169c/d/e/g/h/i/j/k (floor through pull verdicts).
EVIDENCE_FLOOR_VERSION = "0.3.165"

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
        # design/177 — delete causal densify
        "paper_delete_start",
        "paper_delete_done",
        "paper_delete_conflict",
        "papers_residual_kinds",
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
        # design/176 — focus practice speaking clock
        "focus_session_start",
        "focus_session_end",
        "focus_block_done",
        "focus_day_success",
        # design/178 — worker wake causal densify
        "worker_wake_start",
        "worker_wake_done",
        "worker_config_mismatch",
        # design/179
        "sweep_kill_decision",
        "ingest_poll_terminal",
        # design/180 — figure hydrate reliability
        "figure_png_req",
        "figure_png_done",
        # design/184 — ingest intermediate TTL purge
        "ingest_artifact_deleted",
        "ingest_artifact_purge_tick",
        # design/185 — local SoT handoff wipe
        "paper_handoff_start",
        "paper_handoff_done",
        "paper_cloud_wipe",
        "paper_upload_refused_acked",
        # design/186 — device transfer packs
        "transfer_pack_create",
        "transfer_pack_complete",
        "transfer_pack_download",
        "transfer_pack_deleted",
        "transfer_pack_purge_tick",
        "paper_handoff_abandoned",
        "paper_handoff_abandon_purge_tick",
        "paper_bulk_handoff_start",
        "paper_bulk_handoff_done",
        # design/187 — user artifacts device SoT
        "bookmarks_local_migrate_start",
        "bookmarks_local_migrate_done",
        "bookmarks_cloud_wipe",
        "bookmarks_sync_refused",
        "annotations_local_migrate_start",
        "annotations_local_migrate_done",
        "annotations_cloud_wipe",
        "annotations_sync_refused",
        "shadowing_local_migrate_start",
        "shadowing_local_migrate_done",
        "shadowing_cloud_wipe",
        "shadowing_sync_refused",
        "notes_local_migrate_start",
        "notes_local_migrate_done",
        "notes_cloud_wipe",
        "notes_sync_refused",
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
            "papers_residual_kinds",
            "classify_paper_blob_kind",
            "residual_kind_counts",
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
            "paper_delete_start",
            "paper_delete_conflict",
            "_client_handoff_id",
            "_active_ingest_jobs_for_cache",
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
            # design/178
            "worker_config_ok",
            "wake_outcome",
            "stash_wake_on_job",
            "emit_worker_config_mismatch",
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
        "src/sentence_reading/llm/ingest_worker_wake.py",
        (
            "WakeResult",
            "worker_wake_start",
            "worker_wake_done",
            "worker_config_mismatch",
            "wake_outcome",
            "stash_wake_on_job",
            "wake_fields_from_job",
            "emit_worker_config_mismatch",
        ),
    ),
    (
        "src/sentence_reading/llm/evidence_bus.py",
        ("emit_handoff", "new_handoff_id", "stage_token", "rotate_events", "filter_retained"),
    ),
    (
        "mobile/lib/api/client.dart",
        (
            "ingest_poll_terminal",
            "will_refresh_library",
            "figure_png_req",
            "figure_png_done",
            "fetchFigurePng",
        ),
    ),
    (
        "mobile/lib/state/library_controller.dart",
        (
            "after_ingest_fail",
            "clearError",
            "preserved_error",
            "_withFigureNetGate",
            "_hydrateActive",
            "fetchFigurePng",
            "per_png",
        ),
    ),
    (
        "src/sentence_reading/api/app.py",
        (
            "cache_figure_png",
            "figure_png_lookup",
            "figure_png_done",
            "session_ensured",
            "_ingest_artifact_ttl_loop",
            "ingest_artifact_purge_tick",
            "_transfer_pack_ttl_loop",
            "transfer_pack_purge_tick",
            "_paper_handoff_abandon_loop",
            "paper_handoff_abandon_purge_tick",
        ),
    ),
    (
        "src/sentence_reading/cache/paper_cache.py",
        (
            "figure_png_bytes_with_reason",
            "figure_png_lookup",
            "ensure_session_for_figure_png",
        ),
    ),
    (
        "mobile/lib/state/library_controller.dart",
        (
            "reuse_hydrate_session",
            "noRetryReasons",
            "hydrate_bg_retry",
        ),
    ),
    (
        "scripts/rotate_evidence.py",
        ("rotate_events", "--force"),
    ),
    (
        "src/sentence_reading/llm/ingest_artifact_ttl.py",
        (
            "stamp_terminal_retention",
            "clear_retention_on_reclaim",
            "assert_deletable_object",
            "delete_job_artifacts",
            "purge_all_uids",
            "ingest_artifact_deleted",
        ),
    ),
    (
        "src/sentence_reading/llm/paper_handoff.py",
        (
            "build_handoff_manifest",
            "apply_handoff_ack",
            "refuse_upload_if_acked",
            "paper_cloud_wipe",
            "purge_abandoned_once",
            "paper_handoff_abandoned",
        ),
    ),
    (
        "src/sentence_reading/llm/transfer_pack_gcs.py",
        (
            "assert_deletable_pack_object",
            "create_pack",
            "complete_pack",
            "transfer_pack_create",
            "transfer_pack_complete",
        ),
    ),
    (
        "src/sentence_reading/llm/transfer_pack_ttl.py",
        (
            "purge_once",
            "should_purge_meta",
            "transfer_pack_deleted",
        ),
    ),
    (
        "src/sentence_reading/llm/user_artifacts_local_sot.py",
        (
            "bookmarks_local_sot_enabled",
            "annotations_local_sot_enabled",
            "shadowing_local_sot_enabled",
            "notes_local_sot_enabled",
        ),
    ),
    (
        "src/sentence_reading/llm/shadowing_local_sot.py",
        (
            "wipe_shadowing_and_voice_for_uid",
            "refuse_shadowing_cloud_write_if_local_sot",
        ),
    ),
    (
        "src/sentence_reading/llm/bookmarks_gcs.py",
        (
            "wipe_bookmarks_store",
            "refuse_bookmarks_push_if_local_sot",
        ),
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
        (
            "progress_view",
            "_progressMsgHash",
            "view_side",
            "adoptJobTrace",
            "cache/delete",
            "_breadcrumbTimeout",
            "X-Asr-Handoff-Id",
        ),
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
            "paper_delete_start",
            "paper_delete_done",
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
    (
        "mobile/lib/state/focus_practice_controller.dart",
        (
            "focus_session_start",
            "focus_session_end",
            "focus_block_done",
            "focus_day_success",
            "beginSpeak",
            "endSpeak",
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
