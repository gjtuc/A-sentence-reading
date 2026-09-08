# 187 — User artifacts device SoT (evidence stays cloud)

**Status:** SHIPPED phases A–E (0.3.184+)  
**Depends:** [185](185-local-paper-sot.md) paper wipe · [186](186-device-transfer-pack.md) transfer pack expand (E)

## Intent

Cloud keeps **analysis pipelines** + **evidence/ops** only.  
Device is SoT for: bookmarks, annotations, shadowing (chunk cache + takes + voice), notes store (no revived mobile notes UI).

## Locked judgments

| # | Lock |
|---|------|
| J1 | Evidence/ops stay cloud; never move audio/text of user artifacts into evidence payloads |
| J2 | Device is SoT for bookmarks / annotations / shadowing takes+voice+chunk-cache / notes store |
| J3 | Wipe GCS only **after** device write confirmed (migrate ACK). Never wipe-on-fail |
| J4 | When local-SoT on: refuse durable cloud **PUT/push** (anti dual-write resurrection) |
| J5 | GET sync remains for one-shot migrate pull |
| J6 | Cross-device via **186 pack expand (phase E)**; until then device-only (uninstall may lose data) |
| J7 | Mobile v1; web may stay cloud-centric until later |
| J8 | Do **not** revive cancelled mobile keyboard notes UI (141/142) |
| J9 | Paper wipe (185) still must not use `delete_cached_paper` for handoff; artifact migrate wipe = store/prefix delete only |
| J10 | User delete paper on device purges **local** bookmarks/annotations/shadowing for that `cache_id` |
| J11 | Chunk **build** stays server (Gemini); cache plan JSON on device after success |
| J12 | Kill switches: `ASR_BOOKMARKS_LOCAL_SOT`, `ASR_ANNOTATIONS_LOCAL_SOT`, `ASR_SHADOWING_LOCAL_SOT`, `ASR_NOTES_LOCAL_SOT` (default on; `0` = legacy cloud sync) |

## Phases

| Phase | Artifact | Migrate wipe target |
|-------|----------|---------------------|
| A | Bookmarks | `users/{uid}/bookmarks/store_v1.json` |
| B | Annotations | `users/{uid}/annotations/store_v1.json` |
| C | Shadowing + voice | `shadowing/` + referenced `voice/` blobs |
| D | Notes | `users/{uid}/notes/store_v2.json` |
| E | 186 pack | Include per-paper user artifacts in transfer pack |

## Env / status

| Flag | `/api/status` key |
|------|-------------------|
| `ASR_BOOKMARKS_LOCAL_SOT` | `bookmarks_local_sot` |
| `ASR_ANNOTATIONS_LOCAL_SOT` | `annotations_local_sot` |
| `ASR_SHADOWING_LOCAL_SOT` | `shadowing_local_sot` |
| `ASR_NOTES_LOCAL_SOT` | `notes_local_sot` |

## Evidence (add-only)

`bookmarks_local_migrate_start|done`, `bookmarks_cloud_wipe`, `bookmarks_sync_refused`  
`annotations_local_migrate_*`, `annotations_cloud_wipe`, `annotations_sync_refused`  
`shadowing_local_migrate_*`, `shadowing_cloud_wipe`, `shadowing_sync_refused`  
`notes_local_migrate_*`, `notes_cloud_wipe`, `notes_sync_refused`

## Hazards

| # | Hazard | Mitigation |
|---|--------|------------|
| H1 | Dual-write after wipe | Refuse PUT when local-SoT |
| H2 | Prefs lost on uninstall | 186 pack (E); UI notice |
| H3 | Voice biometric | Local files only; no evidence audio |
| H4 | Ink prefs size | Annotations prefer disk file when large |
| H5 | Web still syncs | v1 mobile; web deferred |

## Relation to 185 §2.2

Former “stays on cloud” rows for notes/bookmarks/annotations/shadowing/voice are **legacy until 187 phases land** — after migrate+wipe they are empty on GCS. Evidence/ops/ingest staging/transfer_packs remain cloud.
