# 292 — API/worker role gates after pair ship

Version: **0.3.287** · Status: **locked**  
Amends [291](291-ship-staged-source-bash-apk.md) · [290](290-ship-orchestrator-pair-finish.md)  
Incident: 2026-09-16 0.3.286 — pair phase B redeployed **API** service with `ASR_SERVICE_ROLE=worker` (env left from worker script defaults via inherited `ASR_CLOUD_RUN_SERVICE`). `/api/status` returned worker JSON; product API broken until image redeploy with `role=api`.

## Why 291 was not enough

| Gap | What happened |
|-----|----------------|
| Worker script force-service | Fixed late; phase B still ran once against API |
| Success = image digest only | Did not notice API became worker |
| No preflight role×service matrix | `role=worker` + service=`asr-sentence-reading` allowed |

## Rules

### G1 — deploy preflight (role × service)

`deploy_cloud_run.sh` before `gcloud run deploy`:

- If `ASR_SERVICE_ROLE` ∈ {worker} **and** service name does **not** contain `worker` → exit 2.  
- If service name contains `worker` **and** role is empty/api → exit 2.

`deploy_cloud_run_worker.sh` already forces `*worker*` service (291); keep + call shared check.

### G2 — live API role probe

`scripts/check_api_service_role.py`:

- GET API `/api/status`.  
- Fail if HTTP body has `service_role=worker`.  
- Fail if `version` missing/empty (worker stub often has no product version).  
- OK when version present and role is missing/api/empty (api default).

### G3 — pair + ship_release gates

After phase A (API deploy): run G2; abort before worker if fail.  
After phase B: run G2 again (API must still be api).  
`ship_release.sh`: after verify_live, run G2 + image digest match.

### G4 — docs

Ship: one version commit → `ship_release.sh` only; no mid-ship ops commits.

## Non-goals

- Changing Cloud Run service names  
- Product API status schema beyond role/version checks  

## Acceptance

1. Contract: deploy script text has role×service refuse.  
2. `check_api_service_role.py` + pair/ship call sites.  
3. README 292.
