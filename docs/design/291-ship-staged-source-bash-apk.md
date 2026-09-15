# 291 — Ship reliability: staged source upload · bash SoT · APK cache fallback

Version: **0.3.286** · Status: **locked**  
Amends [287](287-deploy-apk-wallclock-guards.md) · [289](289-ship-path-hardening.md) · [290](290-ship-orchestrator-pair-finish.md)  
Incident: 2026-09-16 0.3.285 — repeated `gcloud PermissionError` on Uploading sources; pair blocked on HEAD≠live sha (mitigated); `ship_cloud_pair.ps1` parse fail; D5 `PUB_CACHE` → `kernel_snapshot_program` fail until default cache rebuild.

## Why 290 was not enough

| Gap | What happened |
|-----|----------------|
| Retry `--source` from live worktree | Upload still PermissionError (locks / AV / concurrent tools) |
| PS orchestrator | Quoting/`[`/`&&` broke before bash ran |
| D5 always-on Pub/Gradle homes | Cold/partial cache → Flutter kernel snapshot fail |

## Rules

### R1 — Staged tree for Cloud Build upload

`scripts/deploy_cloud_run_pair.sh` (and shared helper):

1. `git archive HEAD` (or `git checkout-index`) into `.tmp_ship_stage/` (clean, no untracked junk).  
2. Run `gcloud run deploy --source` **from that stage directory** (or `gcloud builds submit --tag` then `--image`).  
3. Default `ASR_PAIR_STAGED_SOURCE=1`. Set `0` only for emergency worktree deploy.  
4. Still keep 289 PermissionError retries + 290 settle/worker resume.

### R2 — Bash ship SoT

`scripts/ship_release.sh`:

1. Source env, refuse parallel APK (unless override).  
2. `deploy_cloud_run_pair.sh`  
3. `verify_live_status --expect`  
4. `check_api_worker_images_match.py` (invoke gcloud via bash PATH).  
5. Optional `WITH_APK=1`: after cloud OK, call `build_release_apk.ps1` then optional adb.

`ship_cloud_pair.ps1` becomes a **thin** wrapper: only `bash scripts/ship_release.sh` (no inline bash syntax).

### R3 — APK cache policy

`build_release_apk.ps1`:

1. Default: **do not** force repo `.cache/apk-tooling` (use machine Pub/Gradle).  
2. `-SameDriveCache`: opt-in D5.  
3. On `kernel_snapshot` / compileFlutterBuildRelease fail with SameDriveCache: unset D5 homes and **retry once**.  
4. ASCII-only script strings (no em-dash / ellipsis).

### R4 — Ship commit discipline (docs)

One version-bump commit → push → `ship_release.sh` → only then ops-only follow-ups. Avoid HEAD drift mid-pair.

## Non-goals

- Fixing Windows gcloud PermissionError root in Google tooling  
- Product code changes  

## Acceptance

1. Helper `stage_git_archive` / pair uses `.tmp_ship_stage` when staged flag on.  
2. `ship_release.sh` exists; ps1 only invokes it.  
3. APK helper defaults off SameDriveCache + fallback path in script text.  
4. README 291 + contract tests.
