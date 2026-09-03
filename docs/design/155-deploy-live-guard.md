# design/155 — Deploy live guard (stale overwrite prevention)

## Why

Multiple Cursor chats or old local clones can deploy **older** `app.py` versions over **newer** Cloud Run live, undoing fixes.

## Mechanism

1. **`scripts/session_freshness_guard.py`** — run at **new chat / start of product work** (`allow-same-version`; exit 1 = must pull).
2. **`scripts/pre_deploy_guard.py`** — run before every deploy (local + GitHub CD).
3. **`scripts/hook_block_stale_asr_deploy.py`** — Cursor `beforeShellExecution` deny when deploy would overwrite live.
4. **User hook** `%USERPROFILE%\.cursor\hooks\block-stale-cloud-deploys.py` — routes ASR vs stock; **failClosed**.
5. **`ASR_DEPLOY_GIT_SHA`** — stamped at deploy; `/api/status` → `deploy_git_sha`.
6. **`scripts/deploy_cloud_run.sh`** — calls guard unless `ASR_CD_DRY_RUN=1` or `ASR_SKIP_DEPLOY_GUARD=1`.

## Block rules (fail-closed)

- Local semver **<** live semver → abort
- Local semver **==** live semver → abort (force explicit bump)
- `git rev-list HEAD..origin/main` **> 0** → abort (`git pull` first)
- Dirty working tree → abort
- `mobile/pubspec.yaml` / `config.dart` version ≠ `app.py` → abort
- Live `deploy_git_sha` matches current `HEAD` → abort (no-op redeploy)
- Evidence floor shrink → abort (design/169g)

## Session vs deploy

| Tool | Same version | Dirty | Purpose |
|------|--------------|-------|---------|
| `session_freshness_guard.py` | allow | allow | detect stale chat tree |
| `pre_deploy_guard.py` | block | block | ship only after bump |

## Escape hatches (emergency only)

| Env | Effect |
|-----|--------|
| `ASR_SKIP_DEPLOY_GUARD=1` | Skip entire guard (+ hook allow) |
| `ASR_DEPLOY_ALLOW_DIRTY=1` | Allow uncommitted files |
| `ASR_DEPLOY_ALLOW_SAME_VERSION=1` | Allow redeploy at same semver |
| `ASR_SKIP_EVIDENCE_FLOOR=1` | Skip 169g floor only |

## Agent rules

- Repo: `.cursor/rules/deploy-live-guard.mdc` (`alwaysApply: true`)
- Global: `%USERPROFILE%\.cursor\rules\asr-deploy-live-guard.mdc` (`alwaysApply: true`)

## Verify after deploy

```bash
python scripts/verify_live_status.py --expect 0.3.147 --require-azure-layout --min-pipeline rich-v20
curl -s "$ASR_CLOUD_RUN_URL/api/status" | jq '{version, deploy_git_sha}'
```
