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
        "stall_skipped_live_worker",
        "stall_fired",
        # mirrors (optional)
        "figure_window_empty",
        "figure_blob_miss",
        # design/169c — dense translate / open / poll
        "translate_phase_enter",
        "translate_item_done",
        "translate_call_fail",
        "translate_call_slow",
        "translate_phase_exit",
        "translate_save_ko",
        "open_ko_summary",
        "translate_poll_start",
        "translate_poll_ko",
    }
)
