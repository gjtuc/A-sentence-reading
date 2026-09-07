# 179 — False worker_lost + poll/library causal evidence

**Parent:** [169m](169m-lease-sweeper-reclaim-evidence.md) · [178](178-worker-wake-causal-evidence.md) · [169g](169g-causal-handoff-evidence.md)  
**Status:** DESIGN FROZEN → ship **0.3.162**  
**Trigger:** 2026-09-07 `job_b9fc…` — phone sticky 「처리 worker가 응답하지 않습니다」 + 보관 0건 while GCS `papers/index.json` had 1 entry and worker finished 100%. Evidence (178) proved `reclaim_reason=gcs_lease_alive`, `zombie_risk=true`, `wake_outcome=ok_false`, yet sweeper still called `_fail_job_terminal`. Client never refreshed library after poll 422.

---

## 0. Locked judgments

| # | Judgment |
|---|----------|
| J1 | When reclaim refuses because **another worker still holds a live GCS lease** (`gcs_lease_alive` / `lease_claim_failed` / `already_local`), sweeper **must not** mark `worker_lost`. That is a **false kill**. |
| J2 | Every sweeper reclaim outcome emits **`sweep_kill_decision`** with closed `decision` enum — agents never infer kill from `zombie_risk` alone. |
| J3 | Mobile poll terminal (done+error / 422 / idle 504) emits **`ingest_poll_terminal`** with join fields (not only `client_api_fail`). |
| J4 | After ingest poll **failure**, client **must** still attempt `library_refresh` (`trigger=after_ingest_fail`) so GCS-success + API-false-error does not leave 보관 0건. Sticky banner may remain until dismiss. |
| J5 | `library_refresh` details always include `trigger` snake + `paper_n` + `will_clear_error` (0\|1). |
| J6 | Add-only floor; never shrink 169/177/178 sensors. |
| J7 | Details `_safe_details`-legal only. |

---

## 1. New frozen kinds

```
sweep_kill_decision
ingest_poll_terminal
```

Existing densified: `sweep_decision`, `reclaim_attempt`, `server_job_terminal_error`, `library_refresh`, `client_api_fail`.

---

## 2. Closed enums

### 2.1 `sweep_kill_decision.decision`

| token | meaning |
|-------|---------|
| `marked_lost` | `_fail_job_terminal` applied |
| `skipped_zombie` | reclaim fail but live-lease / already_local — **no kill** (J1) |
| `skipped_reclaim_ok` | reclaim returned ok |
| `skipped_local_running` | `_local_running` on this instance |
| `skipped_already_terminal` | job already done/error |
| `skipped_no_owner` | missing owner |

### 2.2 `ingest_poll_terminal.outcome`

| token | meaning |
|-------|---------|
| `ok` | cache_id present, success return |
| `job_error` | done + ok:false (server error string) |
| `no_cache` | done without durable cache_id |
| `idle_timeout` | 504 idle |
| `http_error` | non-2xx status |
| `cancelled` | user cancel |
| `absolute_timeout` | maxDuration |

### 2.3 `library_refresh.trigger`

`manual` | `ok_fresh` | `after_ingest_ok` | `after_ingest_fail` | `after_delete` | `boot` | `other`

---

## 3. Server — sweeper product + evidence

### 3.1 Zombie reclaim reasons (do not kill)

```
ZOMBIE_RECLAIM_REASONS = frozenset({
  "gcs_lease_alive",
  "lease_claim_failed",
  "already_local",
})
```

### 3.2 After reclaim attempt

```
if reclaim_ok or local_running:
  emit sweep_kill_decision decision=skipped_reclaim_ok|skipped_local_running
  continue
if already terminal:
  emit skipped_already_terminal
  continue
if reclaim_reason in ZOMBIE_RECLAIM_REASONS:
  emit sweep_kill_decision decision=skipped_zombie
       + wake_* + mem/gcs lease ages + reclaim_reason
  continue   # DO NOT _fail_job_terminal
# else true orphan
emit decision=marked_lost
_fail_job_terminal(...)
```

### 3.3 `sweep_kill_decision` details

`decision`, `reclaim_reason`, `reclaim_ok`, `zombie_risk`, `will_mark_lost`,  
`wake_outcome?`, `mem_lease_age_sec`, `gcs_lease_age_sec`, `gcs_lease_missing`,  
`local_running`, `percent`, `cr_rev8?`

---

## 4. Mobile — poll terminal + library honesty

### 4.1 `ingest_poll_terminal` (api/client.dart)

Emit on every poll exit (ok or fail) before throw/return:

```
job_id, percent, outcome, http_status?,
has_cache_id 0|1, will_refresh_library 0|1,
error_token?  // snake from known server codes only; else omit
```

For `job_error`: `will_refresh_library=1` (J4).

### 4.2 `library_controller` after poll fail

```
on AsrApiException (ingest poll path):
  set sticky error (unchanged message)
  await refresh(trigger: after_ingest_fail)  // clears error=null today — KEEP sticky:
    → refresh must accept preserveError / or re-assign error after refresh
```

**Honesty:** `refresh` currently sets `error = null` at start. For `after_ingest_fail`, pass `clearError: false` so banner stays but `papers` updates from GCS.

### 4.3 Densify existing `library_refresh`

Always `details.trigger`, `paper_n`, `fresh`, and when after fail: `preserved_error: 1`.

---

## 5. Join recipe (agent)

```
sweep_kill_decision.decision=skipped_zombie
  + reclaim_attempt.reason=gcs_lease_alive
  + later ingest_terminal 100% / reading_ready
  ≠ client ingest_poll_terminal.outcome=job_error (if API mem poisoned before fix)
  + library_refresh.trigger=after_ingest_fail paper_n>=1
```

Post-fix: `marked_lost` must **never** co-occur with `reclaim_reason=gcs_lease_alive`.

---

## 6. Tests

| # | Assert |
|---|--------|
| T1 | Sweeper path: zombie reason → no `_fail_job_terminal`; emits `skipped_zombie` |
| T2 | True orphan reclaim fail → `marked_lost` still works |
| T3 | Floor + dart mirror for 2 new kinds; pin **0.3.162** |
| T4 | `ingest_poll_terminal` allowlisted; library_refresh keeps trigger |

---

## 7. Out of scope

- Changing Korean banner copy  
- Forcing worker min-instances  
- Auto-clear sticky banner without user X  
- Replaying poisoned in-memory job onto GCS success (worker GCS job already authoritative on next poll from cold API)

---

## 8. Ship checklist

1. Design frozen (this doc)  
2. Code + floor + mobile + tests  
3. Version **0.3.162** (app ×2 + pubspec + config.dart)  
4. `check_evidence_floor` + `pre_deploy_guard`  
5. Deploy (preserve wake URL/secret; capacity profile ok)  
6. `verify_live_status --expect 0.3.162`
