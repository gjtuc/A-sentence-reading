"""design/169 — allowlisted evidence event kinds (agent bus, no UI)."""

from __future__ import annotations

ALLOWED_KINDS = frozenset(
    {
        # lifecycle / decision
        "client_session_start",
        "client_session_end",
        "pref_translate_set",
        "pref_translate_read",
        "pref_shadowing_set",
        "nav_tab",
        "reader_open",
        "reader_cursor",
        "figure_window_req",
        "figure_window_res",
        "ingest_upload_start",
        "ingest_poll_tick",
        "reanalyze_start",
        "reanalyze_pref_snapshot",
        # error / consistency
        "client_api_fail",
        "client_api_timeout",
        "client_unhandled",
        "client_hang",
        "client_silent_catch",
        "translate_poll_exhausted",
        "server_handler_fail",
        "server_job_terminal_error",
        "figure_preserve_miss",
        "figure_meta_write",
        "figure_meta_regress",
        "figure_preserve_skip",
        "ingest_integrity_violation",
        "stall_skipped_live_worker",
        "stall_fired",
        # mirrors (optional)
        "figure_window_empty",
        "figure_blob_miss",
        "figure_data_url_miss",
        # design/169c — dense translate / open / poll
        "translate_phase_enter",
        "translate_item_done",
        "translate_call_fail",
        "translate_call_slow",
        "translate_call_start",
        "translate_call_done",
        "translate_phase_exit",
        "translate_save_ko",
        "open_ko_summary",
        "translate_poll_start",
        "translate_poll_ko",
        # design/169g — causal handoff (phase 2)
        "handoff",
        "progress_view",
        # design/169h — interior checkpoint densify
        "checkpoint",
        # design/169i — artifact transfer ledger
        "artifact_observe",
        "artifact_transfer",
        "artifact_derive",
        "artifact_invalidate",
        # design/169d — full-product dense sensors
        "library_refresh",
        "library_count",
        "paper_delete",
        "ingest_cancel",
        "cache_save_sample",
        "reclaim_seed",
        "download_cache_fail",
        'figures_prior_pull',
        # design/169m — lease / sweeper causality
        "lease_heartbeat",
        "sweep_decision",
        "reclaim_attempt",
        # design/169n — library figure hydrate
        "figure_hydrate_start",
        "figure_hydrate_progress",
        "figure_hydrate_done",
        "figure_hydrate_partial",
        "figure_hydrate_abort",
        # design/169o — post-ingest harmonize residual
        "harmonize_residual_start",
        "harmonize_residual_progress",
        "harmonize_residual_done",
        "harmonize_residual_partial",
        "harmonize_residual_abort",
        # design/169p — shadowing practice prep evidence
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
