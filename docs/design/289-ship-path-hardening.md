# 289 — Ship path hardening (deploy crash · pair resume · APK truth)

Version: **0.3.284** · Status: **locked**  
Amends [287](287-deploy-apk-wallclock-guards.md)  
Incident: 2026-09-15/16 0.3.283 ship — `gcloud PermissionError` after API was live; pair retry blocked by `same_version`; APK built but PS Stop treated Flutter stderr WARNING as failure.

## Why 287 was not enough

| Gap | What happened |
|-----|----------------|
| Retry only Conflict/409 | Upload/`gcloud crashed (PermissionError)` aborted pair |
| Pair assumes API script exit 0 | Live already at HEAD; worker never ran until manual image deploy |
| APK ok = exit code / log regex | Artifact existed; helper exited 1 on stderr NativeCommandError |

## Rules

### S1 — Transient gcloud retry (extends D1)

`deploy_cloud_run.sh`: also retry (same backoff budget) when log matches:

- `PermissionError`
- `gcloud crashed`
- `Errno 13`

Env: still `ASR_DEPLOY_CONFLICT_RETRIES` (name kept; covers transient abort class).

### S2 — Pair resume when API already live

`deploy_cloud_run_pair.sh`:

1. Run API `--source` (or skip rebuild if already live — see below).
2. If API script **non-zero** but live `/api/status` `version` == local app version **and** `deploy_git_sha` prefix matches `HEAD` → **warn and continue** to worker `--image`.
3. If API blocked with `same_version_redeploy_blocked` / `already_deployed_sha` for this HEAD → treat as API ok, worker-only hop.
4. Worker hop always uses API container image (D4).

### S3 — APK success = artifact truth

`build_release_apk.ps1`:

1. Record wall-clock start before flutter.
2. Success if `app-release.apk` exists **and** (exit 0 **or** log Built **or** mtime ≥ start − 60s).
3. Keep stderr Continue wrapper (287 fix).
4. Optional `-WarmCaches`: `flutter pub get` under D5 homes before release build (first-run cold cache).

### S4 — Ship order (docs / checklist)

1. freshness → bump → floor/tests → commit → push  
2. `bash scripts/deploy_cloud_run_pair.sh` only  
3. `verify_live_status --expect`  
4. `build_release_apk.ps1` (−WarmCaches if cache empty) → adb install  

## Non-goals

- Speeding Cloud Build / Gradle themselves  
- Product version bump (ops-only)  
- Changing design/155 guards  

## Acceptance

1. Synthetic log with PermissionError would retry (contract test on script text).  
2. Pair script continues when live sha/version matches HEAD after API fail.  
3. APK helper treats fresh apk path as success even if flutter exit≠0 with JVM warning noise.  
4. README row 289.
