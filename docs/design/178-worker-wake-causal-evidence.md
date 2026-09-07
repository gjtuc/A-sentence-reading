# 178 — Worker wake / config mismatch causal evidence

**Parent:** [169g](169g-causal-handoff-evidence.md) · [169m](169m-lease-sweeper-reclaim-evidence.md) · [173c](173-capacity-isolation-roadmap.md) · [177](177-paper-delete-causal-evidence.md)  
**Status:** DESIGN FROZEN → ship **0.3.161**  
**Trigger:** 2026-09-07 upload showed 「처리 worker가 응답하지 않습니다」 while evidence only had `reclaim_reason: worker_wake_failed` — **cannot distinguish** `not_configured` vs HTTP timeout vs cold start vs `ok:false`. Live `/api/status` had `ingest_inline:false` + `ingest_worker:false` (side channel), not joinable from the job timeline alone.

**UI product change:** none (banner text unchanged). Honesty is in evidence + deploy fail-closed.

---

## 0. Locked judgments

| # | Judgment |
|---|----------|
| J1 | Every wake attempt emits **`worker_wake_start` → `worker_wake_done`** with the **same** `job_id` / optional `trace_id` / `wake_path`. |
| J2 | `wake_outcome` is a **closed enum** (snake). Never collapse to bool-only in evidence. |
| J3 | `reclaim_attempt` with `worker_wake*` **must** carry the same wake fields (`wake_outcome`, `http_status`/`wake_http_status`, `elapsed_ms`, `has_url`, `has_secret`, `configured`). |
| J4 | `server_job_terminal_error` / sweeper `worker_lost` **must** echo `_last_wake_*` stashed on the job. |
| J5 | If `ingest_inline=0` and worker not configured → emit **`worker_config_mismatch`** (severity=error) on spawn/reclaim and throttled on `/api/status`. |
| J6 | `/api/status` densifies: `ingest_worker_url_set`, `ingest_worker_secret_set`, `worker_config_ok` (bool). |
| J7 | **Deploy fail-closed:** `ASR_INGEST_INLINE=0` without both `ASR_WORKER_URL` + `ASR_WORKER_SECRET` → `pre_deploy_guard` / `deploy_cloud_run.sh` exit ≠ 0. Capacity profiles with `DEPLOY_WORKER=1` must resolve wake URL before API deploy. |
| J8 | Add-only floor; never shrink 169/177 sensors. |
| J9 | Details remain `_safe_details`-legal (snake tokens + ints/bools). No URL host strings, no secrets, no exception message text — only `exc_class` token. |

---

## 1. New frozen kinds

```
worker_wake_start
worker_wake_done
worker_config_mismatch
```

Existing densified: `reclaim_attempt`, `server_job_terminal_error`, `sweep_decision`, `handoff` (optional `client_upload→worker_wake`).

---

## 2. Closed enum — `wake_outcome`

| token | meaning |
|-------|---------|
| `ok` | HTTP 200 and body `ok:true` |
| `missing_ids` | empty job_id or owner_uid |
| `not_configured` | URL and/or secret missing (`has_url`/`has_secret` flags) |
| `http_error` | non-200 response (`wake_http_status` set) |
| `ok_false` | 200 but body `ok` falsy |
| `timeout` | httpx timeout |
| `connect_error` | connect/network class |
| `json_error` | response JSON parse fail |
| `exception` | other (`exc_class` set) |

`wake_path` enum: `spawn` | `reclaim` | `status_probe` | `manual`.

---

## 3. Wake contract (`ingest_worker_wake.py`)

### 3.1 Return type

```python
@dataclass(frozen=True)
class WakeResult:
    ok: bool
    outcome: str
    elapsed_ms: int
    has_url: bool
    has_secret: bool
    configured: bool
    http_status: int | None = None
    exc_class: str = ""
    response_ok: bool | None = None
    wake_path: str = "spawn"
```

`wake_ingest_worker(...) -> WakeResult` (callers use `.ok`).

### 3.2 Emit sequence

```
worker_wake_start {
  wake_path, configured, has_url, has_secret,
  ingest_inline: 0|1
}
  → HTTP or early return
worker_wake_done {
  wake_outcome, elapsed_ms, wake_path,
  configured, has_url, has_secret,
  wake_http_status?, exc_class?, response_ok?,
  ok
}
```

Top-level event `http_status` when known. `ok` field = WakeResult.ok.

### 3.3 Job stash (API `_JOBS`)

After each wake:

```
_last_wake_outcome
_last_wake_path
_last_wake_elapsed_ms
_last_wake_http_status   # int or omit
_last_wake_configured    # bool
_last_wake_has_url
_last_wake_has_secret
_last_wake_exc_class
```

---

## 4. Config mismatch

### 4.1 Predicate

```
mismatch = (not ingest_inline_enabled()) and (not ingest_worker_configured())
worker_config_ok = not mismatch
```

### 4.2 `worker_config_mismatch` details

```
ingest_inline: 0
configured: 0|1 → use has_url/has_secret
has_url, has_secret
wake_path | probe_path: spawn|reclaim|status
capacity_profile?: snake token (hyphens → underscores)
```

### 4.3 Emit policy

| path | policy |
|------|--------|
| spawn (`_spawn_ingest_worker`) | **always** if mismatch |
| reclaim wake fail `not_configured` | **always** |
| `/api/status` | throttle ≥ **60s** per process |

---

## 5. Reclaim + terminal join

### 5.1 `_reclaim_ingest_job_from_gcs` (inline=0 branch)

```
ok_wake = await wake(..., wake_path="reclaim")
stash wake fields on job
_emit("worker_wake" | "worker_wake_failed", extra=wake.details())
```

### 5.2 Sweeper → `_fail_job_terminal` / `server_job_terminal_error`

Pass-through keys (add to existing 169m allowlist):

```
wake_outcome, wake_path, wake_elapsed_ms, wake_http_status,
wake_configured, wake_has_url, wake_has_secret, wake_exc_class,
reclaim_reason
```

---

## 6. `/api/status` densify

```json
{
  "ingest_inline": false,
  "ingest_worker": false,
  "ingest_worker_url_set": false,
  "ingest_worker_secret_set": false,
  "worker_config_ok": false
}
```

`worker_config_ok == false` ⇒ agents treat as **P0 config**, not cold-start guess.

---

## 7. Deploy fail-closed (detection at ship time)

1. `scripts/deploy_cloud_run.sh`: if `ASR_INGEST_INLINE` in `0|false|off|no` and (URL or secret empty) → **exit 2** before `gcloud`.
2. `scripts/pre_deploy_guard.py`: same check against intended env (local + documented).
3. `scripts/deploy_capacity_profile.sh`: when `DEPLOY_WORKER=1` and inline=0, set  
   `ASR_WORKER_URL` from `ASR_WORKER_URL` or default  
   `https://${ASR_WORKER_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app`  
   and require `ASR_WORKER_SECRET` from env file / `gc_automation.env`.

WHY: capacity profile deploys that omit URL from `--env-vars-file` **wipe** prior wake env → live `ingest_worker:false`.

---

## 8. Join recipe (agent)

```
upload / spawn
  → worker_config_mismatch?           # P0 config
  → worker_wake_start.wake_path=spawn
  → worker_wake_done.wake_outcome=…
reclaim_attempt.reason=worker_wake_failed
  + same wake_outcome / has_url / has_secret
server_job_terminal_error
  + wake_outcome + reclaim_reason
status.worker_config_ok == false
```

Verdict table:

| wake_outcome | meaning |
|--------------|---------|
| `not_configured` | deploy/env wiring |
| `timeout` / `connect_error` | cold start / network / worker down |
| `http_error` | auth/path/revision |
| `ok_false` | worker refused job |
| `ok` then later `worker_lost` | lease/runtime after successful wake |

---

## 9. Tests

| # | Assert |
|---|--------|
| T1 | WakeResult outcomes: not_configured / http_error / timeout / ok / ok_false |
| T2 | Floor contains 3 new kinds; py↔dart mirror |
| T3 | Terminal details keep `wake_outcome` |
| T4 | deploy guard rejects inline=0 without URL+secret |
| T5 | Floor version pin **0.3.161** |

---

## 10. Out of scope

- Changing Korean banner copy
- Forcing `min-instances=1` on worker
- Auto-fallback to inline on mismatch (product policy later; sensors first)
- Logging raw worker URL or secret material

---

## 11. Ship checklist

1. Design frozen (this doc)  
2. Code + floor + tests  
3. Version **0.3.161** (app ×2 + pubspec + config.dart)  
4. `check_evidence_floor` + `pre_deploy_guard` exit 0  
5. Deploy with worker URL+secret present → live `worker_config_ok:true` when inline=0  
6. `verify_live_status --expect 0.3.161`
