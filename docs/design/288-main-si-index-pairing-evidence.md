# 288 — Main+SI index/pairing evidence densify (overkill)

Version: **0.3.283** · Status: **locked**  
Amends [279](279-soft-hide-allowlist-mate-merge-pair.md) · [282](282-merge-reader-honesty.md) · [284](284-ingest-dual-handoff-notify-evidence.md)  
Incident: 2026-09-15 Main upload `c97ed6ef90ae5` then SI `c3946e79fa02f` — library showed SI-only / skip_multi_main; title/role evidence thin; SI figures 0.

## Why

Existing sensors (`library_pairing_pass`, merge/reader honesty, `poll_cache_vs_index`) prove **pairing counters** and handoff forks, but **not**:

1. Local `upsertIndex` RMW races / silent drops while session still on disk  
2. Harmonize residual poll publishing **remote-only** (no `mergeRemoteWithLocal`)  
3. Focused `skip_multi_main` signal (buried in pass details)  
4. `open_ko_summary` / `figure_meta_write` without `doc_role`  
5. SI figure extract outcome as a first-class kind  
6. Named “title pipeline empty” when open has no KO / empty role  

Product vanish fix is **out of scope** until these prove the race in JSONL.

## Densify map

### P0 — enrich existing

| Kind | Add fields |
|------|------------|
| `open_ko_summary` | `doc_role`, `role_empty` 0\|1 |
| `figure_meta_write` | `doc_role`, `supplementary` 0\|1 |
| `library_pairing_pass` | keep counters; `trigger` includes `harmonize_poll` |

### E1 — `library_index_upsert` (boundary)

Every disk index upsert/remove: `op`, `index_n_before`/`after`, `id` (cache_id), `role`, `has_pair` 0\|1, `caller` snake.

### E2 — `library_index_race` (error)

Upsert/remove unexpectedly drops another id that still `hasSession` → `ok=false`, `code=index_upsert_lost_id`.

### E3 — `library_publish_no_merge` (error/sample)

Harmonize poll path: remote list publish without local merge; if any local-with-session missing from remote → `ok=false`, `code=harmonize_poll_no_merge`.

### E4 — `pairing_skip_multi` (error)

When `skip_multi_main_n>0` or `skip_multi_si_n>0` after pass → focused emit (`ok=false`, `code=pairing_skip_multi`).

### E5 — `figure_extract_done` (boundary)

After ingest `extract_figures`: `doc_role`, `fig_n`, `supplementary`, `empty`.

### E6 — `title_pipeline_empty` (consistency)

On open: empty `doc_role` and/or `ko_s==0` with sentences present → `ok=false`, `code=title_pipeline_empty`.

### E7 — agent verdicts (`evidence_verdict`)

| Verdict | Trigger |
|---------|---------|
| `harmonize_poll_dropped_local` | E3 ok=false |
| `skip_multi_main_blocks_pair` | E4 or pass skip_multi_main_n>0 |
| `open_without_doc_role` | open `role_empty=1` |
| `si_figure_zero_after_extract` | E5 supplementary+empty |
| `index_upsert_lost_id` | E2 |

## Floor / twins

- Allowlist twins + **add-only** `FROZEN_KINDS`  
- Markers: `library_controller`, `paper_disk_store`, `app.py`, `paper_cache`

## Non-goals

- Changing 1+1 pairing / auto-merge  
- Fixing product vanish (follow-up chip after sensors)  
- Shrinking evidence floor  
- design/287 ops (already parallel)

## Acceptance

1. Re-upload Main+SI: JSONL shows E1 on handoff/refresh; E3 if harmonize poll omits local session; E4 if skip_multi_main.  
2. Open main/SI: `open_ko_summary.doc_role` present; E6 if empty.  
3. SI extract: `figure_extract_done` with fig_n/empty.  
4. `compute_pair_index_verdicts` (or cache verdicts) fires the five codes on synthetic events.  
5. `python scripts/check_evidence_floor.py` exit 0.
