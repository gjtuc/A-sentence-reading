# 293 — Ship preflight checklist (encode the smooth path)

Version: **0.3.288** · Status: **locked**  
Amends [291](291-ship-staged-source-bash-apk.md) · [292](292-api-worker-role-gates.md)  
Context: 0.3.287 ship was smooth when agents followed one-bump → `ship_release.sh` → APK-after-cloud. Residual risk is **skipping** that path, not missing sensors.

## Why

287–292 already harden upload, pair, roles, APK caches. Smoothness now fails when:

- tracked tree dirty mid-ship  
- APK runs beside cloud  
- people call raw deploy scripts instead of `ship_release`  
- version/HEAD not pushed before deploy  

## Rules

### F1 — `ship_release.sh` preflight

Before pair:

1. Print fixed checklist (8 lines).  
2. Refuse if `git status --porcelain` shows **tracked** modifications (` M` / `M ` / `MM` etc.); untracked OK.  
3. Refuse if `HEAD` ≠ `origin/main` (not pushed) unless `ASR_SHIP_ALLOW_UNPUSHED=1`.  
4. Keep existing parallel-APK refuse (291).  
5. Confirm local app/pubspec/config versions match (python one-liner).

### F2 — Docs only reminder

Design README: prefer `ship_release.sh`; raw pair only for debug.

## Non-goals

- New Cloud Run behavior  
- Product version bump in this chip alone  
- Blocking all untracked files  

## Acceptance

1. `ship_release.sh` contains preflight + tracked-dirty / unpushed checks.  
2. Contract test + README 293.
