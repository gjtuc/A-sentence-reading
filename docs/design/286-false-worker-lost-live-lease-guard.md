# 286 — False worker_lost live-lease guard + overkill sensors

Version: **0.3.282** · Status: **locked**  
Amends [179](179-false-worker-lost-poll-library-evidence.md) · [178](178-worker-wake-causal-evidence.md) · [169m](169m-lease-sweeper-observability.md)  
Incident: 2026-09-15 `job_a8ecfe709d70` — spawn wake ok + progress, reclaim wake `ok_false`, sweeper `marked_lost` while `gcs/mem_lease_age_sec≈-274`, then ingest continued to save.

## Why

179 skipped kill only for reclaim_reason ∈ `{gcs_lease_alive, lease_claim_failed, already_local}`.  
Tonight: concurrent spawn claimed lease during a long reclaim wake → wake body `ok:false` → reason `worker_wake_failed` → **false kill** even though GCS lease was live.  
`track_verdict.false_worker_lost_stale_mem_lease` also missed (needs `gcs_lease_alive` or mem expired + GCS live).

## Product (P0)

**Invariant:** never `_fail_job_terminal` / `marked_lost` when **GCS lease is still valid** (`gcs_lease_missing` false and `gcs_lease_age_sec < 0`), regardless of `reclaim_reason`.

Optional also skip when mem lease still valid (`mem_lease_age_sec < 0`) **and** same `mem_tok8`/`gcs_tok8` non-empty (belt).

New `sweep_kill_decision.decision` tokens:

| token | meaning |
|-------|---------|
| `skipped_live_gcs_lease` | reclaim fail but GCS lease age &lt; 0 |
| `skipped_live_mem_lease` | reclaim fail but mem lease age &lt; 0 (+ tok match preferred) |

Keep existing `skipped_zombie` for 179 reason-set.

True orphan path unchanged: lease missing **or** age ≥ 0 (expired) **and** reclaim/wake failed → `marked_lost` still allowed.

## Evidence densify (overkill)

### E1 — densify `sweep_kill_decision`

Always include: `live_gcs` 0|1, `live_mem` 0|1, `gcs_lease_age_sec`, `mem_lease_age_sec`, `reclaim_reason`, `wake_outcome`, `decision`.

When decision is `skipped_live_gcs_lease` / `skipped_live_mem_lease`: `ok=true`, severity boundary, `code=false_lost_blocked`.

### E2 — new kind `false_worker_lost_guard` (boundary)

Emit **immediately before** skip when live lease blocks a would-be kill (same moment as skipped_* decision).

| Field | Meaning |
|-------|---------|
| `blocked` | 1 |
| `would_mark` | 1 |
| `reclaim_reason` | snake |
| `wake_outcome` | snake |
| `live_gcs` / `live_mem` | 0\|1 |
| `gcs_lease_age_sec` / `mem_lease_age_sec` | int |

`ok=true`, `code=false_lost_blocked`.

### E3 — new kind `false_worker_lost_suspect` (error)

Emit on `server_job_terminal_error` path **if** somehow still marking lost while live GCS lease (should be unreachable after P0; sensor for regressions).

`ok=false`, `code=false_lost_marked`, severity error.

### E4 — densify worker `/internal/run-job` + wake

Worker JSON when `ok=false`: add snake `error` from `_last_reclaim_reason` (e.g. `gcs_lease_alive`, `lease_claim_failed`, `already_local`, `bad_request`).

`worker_wake_done` details: copy `error` → `wake_error` (prefixed/snake allowlist) when present.

### E5 — new kind `post_terminal_ingest_progress` (consistency)

When `progress_view` / stage advance is recorded for a job that already has `error` / terminal worker_lost in mem: emit once per job (rate-limit) with `after_terminal=1`, `percent`, `stage` snake truncate.

`ok=false`, `code=zombie_progress`.

### E6 — `track_verdict` (agent pull)

Add:

1. `false_worker_lost_live_gcs` — terminal `worker_lost` + `gcs_lease_age_sec < 0`
2. `false_worker_lost_wake_fail_live` — terminal + `reclaim_reason=worker_wake_failed` + (`gcs_age<0` or `mem_age<0`)
3. Keep existing `zombie_worker` / `false_worker_lost_stale_mem_lease`

Fix stale detector: also fire when **both** ages &lt; 0 (alive) on worker_lost terminal.

## Floor / twins

- `evidence_kinds.py` + `evidence_kinds.dart`: `false_worker_lost_guard`, `false_worker_lost_suspect`, `post_terminal_ingest_progress`
- `FROZEN_KINDS` + emit markers
- Ops kinds twin if ops bus lists kinds

## Tests

| Test | Assert |
|------|--------|
| `tests/test_design_286_*.py` | design locked · kinds · markers · version 0.3.282 |
| extend `test_sweep_kill_179` / new | live GCS age&lt;0 + wake_fail → will_mark false |
| `test_track_verdict` | live gcs ages fire new verdicts |
| wake ok_false carries wake_error when body has error |

## Non-goals

- Changing lease TTL / heartbeat interval
- Forcing ingest_inline=1
- Main/SI / handoff notify product (285)

## Acceptance

1. Reproduce tonight pattern: reclaim wake `ok_false` + live GCS lease → **no** phone worker_lost; `false_worker_lost_guard` + `skipped_live_gcs_lease` present.
2. True orphan (lease expired/missing + wake fail) still `marked_lost`.
3. If progress continues after a historical false terminal, `post_terminal_ingest_progress` or `zombie_worker` verdict appears on pull.
