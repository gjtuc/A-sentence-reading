# 169d — Full-product dense evidence

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169c](169c-dense-translate-open-auth.md) · [169-audit-checklist.md](169-audit-checklist.md)  
**Version:** 0.3.125+  
**UI:** 없음

---

## Scope

Fill remaining **P0/P1** audit rows across library, figures, ingest, hang, reclaim, cache download — not web (169e).

| Area | kinds |
|------|--------|
| Library | `library_refresh`, `library_count`, `paper_delete` |
| Figures | `figure_window_req`/`res`, `figure_window_empty` (server mirror) |
| Ingest | `ingest_cancel`, poll tick already; hang → `client_hang` |
| Reanalyze | `figures_prior_pull`, `reanalyze_start` server |
| Cache | `cache_save_sample`, `download_cache_fail`, `reclaim_seed` |
| Terminal | `server_job_terminal_error`, `server_handler_fail` |
| Stall | `stall_skipped_live_worker` (sample) |

Agent pull:

```bash
python scripts/pull_evidence.py --since 2h --kind library_refresh,library_count,figure_window_res,figure_window_empty,ingest_cancel,reclaim_seed,download_cache_fail,server_job_terminal_error,client_hang,open_ko_summary,translate_item_done
```

## Non-goals

- Web `static/evidence.js` (169e)
- Admin/user UI
- Sentence text / PDF bytes in details
