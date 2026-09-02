# 169m — lease / sweeper / reclaim observability

**Version:** 0.3.140  
**Goal:** Diagnose `worker_lost` before changing kill policy.

## Questions answered

1. Which Cloud Run instance ran sweeper vs worker? (`cr_rev8`)
2. Was memory `lease_until` expired while GCS lease still alive? (`mem_lease_age_sec` vs `gcs_lease_age_sec`)
3. Why did reclaim fail? (`reclaim_reason`: `gcs_lease_alive` | `upload_missing` | …)
4. Did heartbeat still run? (`lease_heartbeat` / `hb_seq`)

## Kinds (evidence + ops)

| kind | when |
|------|------|
| `lease_heartbeat` | every 4th HB + force on exit |
| `sweep_decision` | `action=none` 1/20; `reclaim` + `reclaim_result` always |
| `reclaim_attempt` | every reclaim exit (now dual-bus) |
| `server_job_terminal_error` | enriched with lease snapshot |

## Verdict shortcuts (`track_verdict`)

- `false_worker_lost_stale_mem_lease` — `gcs_lease_alive` or mem expired + GCS still valid
- `true_worker_orphaned` — `gcs_lease_age_sec > 0`

## Policy note

Sensors only in 0.3.140 — still marks `worker_lost` after reclaim fail (including `gcs_lease_alive`). Fix kill policy in a later version after one live reproduce confirms the timeline.
