# 287 — Deploy / APK wall-clock guards



Version: **ops** · Status: **locked**  

Incident: 2026-09-15 0.3.282 ship — commit/push fast; Cloud Run ~6–10m ×2; APK failed twice then ~36m non-incremental.



## Hazards (measured)



| Step | Cost | Failure mode |

|------|------|----------------|

| `gcloud run deploy --source` | ~6–10 min each | Parallel API+worker → `ABORTED: Conflict for resource` (wasted attempt) |

| Second `--source` for worker | another ~6–10 min | Same Dockerfile rebuilt; image already exists on API |

| `flutter build apk --release` | ~15–35 min | Kotlin incremental cache: Pub on `C:` vs project on `D:` → `Could not close incremental caches` |

| Clean + rebuild after fail | doubles wall clock | Same incremental bug recurs without pin |



## Product / ops rules



### D1 — Cloud Run conflict retry



`scripts/deploy_cloud_run.sh`: on `ABORTED: Conflict for resource`, sleep backoff and retry up to 4 attempts (API and worker share this).



Prefer **API then worker** (sequential) when both need ship; parallel only with retry armed.



### D2 — Pin Kotlin non-incremental for release APK



`mobile/android/gradle.properties`:



```

kotlin.incremental=false

kotlin.incremental.java=false

```



WHY: Windows multi-root (Pub cache `C:` + repo `D:`) breaks relocatable incremental maps. Slightly slower happy path ≪ failed×2 + clean.



### D3 — APK build helper



`scripts/build_release_apk.ps1`:



1. Pin Pub/Gradle homes under repo `.cache/apk-tooling` (**D5**)

2. `gradlew --stop`

3. Ensure D2 props present

4. `flutter build apk --release`

5. On incremental-cache failure: wipe `mobile/build` (+ android caches), retry **once**



Copy success APK to `data/sentence-reading-latest.apk` when present.



### D4 — Pair deploy: one build, two services (**stronger**)



`scripts/deploy_cloud_run_pair.sh`:



1. Deploy **API** with `--source` (one Cloud Build)

2. Read `spec.template.spec.containers[0].image` from API

3. Deploy **worker** with `ASR_DEPLOY_IMAGE=<that>` → `--image` (no second build)



`deploy_cloud_run.sh` honors `ASR_DEPLOY_IMAGE` when set.



Expected save: ~one full Cloud Build (~6–10 min) + no parallel Conflict.



### D5 — Same-drive Pub/Gradle for APK (**stronger**)



`build_release_apk.ps1` sets:



- `PUB_CACHE=<repo>/.cache/apk-tooling/pub-cache`

- `GRADLE_USER_HOME=<repo>/.cache/apk-tooling/gradle-user-home`



WHY: eliminates C:/D: “different roots” at the source; D2 remains belt-and-suspenders.



## Note (ops landed)



D4 (`deploy_cloud_run_pair.sh` + `ASR_DEPLOY_IMAGE`) and D5 (repo-local `PUB_CACHE` / `GRADLE_USER_HOME` in `build_release_apk.ps1`) **already landed** in-tree. This doc remains the ops SoT; do not re-implement.



## Non-goals



- Speeding Cloud Build itself (remote Dockerfile)

- Changing design/155 version guards

- Evidence densify for main+SI (design/288)



## Acceptance



1. Parallel worker deploy that hits Conflict eventually succeeds without manual re-run.

2. Release APK build on this machine does not fail on `Could not close incremental caches` in the common path.

3. `deploy_cloud_run_pair.sh` deploys worker via `--image` after API `--source`.

4. APK helper uses repo-local `PUB_CACHE` / `GRADLE_USER_HOME`.

5. Design row in `docs/design/README.md`.


