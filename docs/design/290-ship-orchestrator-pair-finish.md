# 290 — Ship orchestrator + pair must finish worker

Version: **0.3.285** · Status: **locked**  
Amends [287](287-deploy-apk-wallclock-guards.md) · [289](289-ship-path-hardening.md)  
Incident: 2026-09-16 0.3.284 — PermissionError retried; API became live; pair log truncated and **worker hop did not run** until manual image deploy.

## Why 289 was not enough

| Gap | What happened |
|-----|----------------|
| Pair assumes continuous shell after API | Process/log cut mid-retry; no forced worker stage |
| API crash can still leave revision live | Need **settle wait** + recheck live before abort |
| “Deploy done” = script exit | Must be `verify_live` + **API image == worker image** |
| APK ‖ Cloud Run | Concurrent ship risks gcloud upload PermissionError |

## Rules

### P1 — Pair two-phase with settle

`deploy_cloud_run_pair.sh`:

1. Phase A: API `--source` (289 retries).  
2. If A rc≠0: sleep `ASR_PAIR_SETTLE_SEC` (default 20), recheck live version+sha.  
3. If live matches HEAD → continue; else abort.  
4. Phase B: **always** run worker `--image` when Phase A ok **or** live matches (never skip B after A success/live).  
5. Append structured lines to `.tmp_pair_deploy.log`: `phase=a|b rc=…`.  
6. Phase C: assert API container image digest == worker image digest; print `pair_ok=1`.

### P2 — Ship orchestrator

`scripts/ship_cloud_pair.ps1` (Windows SoT for agents):

1. Refuse if `ASR_SHIP_ALLOW_PARALLEL_APK=1` not set **and** a `flutter build apk` / `build_release_apk` process is running.  
2. `bash scripts/deploy_cloud_run_pair.sh`  
3. `python scripts/verify_live_status.py --expect <local version>`  
4. Python/gcloud check API image == worker image  
5. Exit non-zero unless all pass  

Optional later: `-WithApk` runs APK **after** cloud steps only.

### P3 — Docs / checklist

Ship order: freshness → bump → commit → push → **`ship_cloud_pair.ps1`** → (optional) `build_release_apk.ps1` → adb.  
Do not call raw `deploy_cloud_run.sh` + worker in parallel.

## Non-goals

- Eliminating gcloud PermissionError root cause on Windows  
- Product version bumps in this chip alone  
- Changing 155 guards  

## Acceptance

1. Pair script text has settle sleep + phase B always after live match + image equality check.  
2. `ship_cloud_pair.ps1` exists and calls pair + verify.  
3. Contract tests + README 290.
