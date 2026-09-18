# 316 — GitHub CD uses the pair orchestrator

**Version:** 0.3.313 · Status: **locked** (ops; no product bump)  
Amends [32](32-github-cd.md) · [173](173-capacity-isolation-roadmap.md) · [287](287-deploy-apk-wallclock-guards.md) · [292](292-api-worker-role-gates.md)

## Why

Local ship is `ship_cloud_pair.ps1` → `ship_release.sh` → `deploy_cloud_run_pair.sh`:
API source deploy, role gate, worker from the **same image digest**, digest match, role gate again.

GitHub CD did not. `deploy-cloud-run.yml` ran a capacity profile that either
skipped the worker or built it with a **second `--source`**.
`deploy-cloud-run-worker.yml` could ship the worker alone. Worker code lives
in the API image, so a solo worker hop either reused a stale digest or built
a different one. That is the 292 incident class.

CD stays gated by `ASR_CD_ENABLED` (default off). This chip only closes the
path if someone turns it on.

## Locked

1. `DEPLOY_WORKER=1` capacity profiles call `deploy_cloud_run_pair.sh`. They
   must not `gcloud run deploy --source` the worker a second time.
2. Solo worker CD does not call `gcloud`. It prints the pair workflow name
   and exits 0.
3. Both workflows share concurrency group `asr-cloud-pair`.
4. Main CD path filters include worker sources and the pair script.
5. Local `ship_release.sh` is unchanged.

## Not this chip

- Turning `ASR_CD_ENABLED` on
- Changing the default capacity profile (`turn0-baseline-off` stays API-only)
- Bumping `0.3.313`

## Test

- capacity script contains `deploy_cloud_run_pair.sh` and does not set
  `ASR_SERVICE_ROLE=worker` before a second `deploy_cloud_run.sh`
- worker workflow has no `deploy_cloud_run_worker.sh` / `setup-gcloud`
- both yml files use `asr-cloud-pair`
