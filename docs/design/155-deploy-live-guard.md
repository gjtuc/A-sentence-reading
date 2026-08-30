# design/155 — Deploy live guard (stale overwrite prevention)

## Why

Multiple Cursor chats or old local clones can deploy **older** `app.py` versions over **newer** Cloud Run live, undoing fixes (e.g. cite `$1`, bookmarks).

## Mechanism

1. **`scripts/pre_deploy_guard.py`** — run before every deploy (local + GitHub CD).
2. **`ASR_DEPLOY_GIT_SHA`** — stamped at deploy time into Cloud Run env; exposed as `/api/status` → `deploy_git_sha`.
3. **`scripts/deploy_cloud_run.sh`** — calls guard unless `ASR_CD_DRY_RUN=1` or `ASR_SKIP_DEPLOY_GUARD=1`.

## Block rules (fail-closed)

- Local semver **<** live semver → abort
- Local semver **==** live semver → abort (force explicit bump)
- `git rev-list HEAD..origin/main` **> 0** → abort (`git pull` first)
- Dirty working tree → abort
- `mobile/pubspec.yaml` version ≠ `app.py` version → abort
- Live `deploy_git_sha` matches current `HEAD` → abort (no-op redeploy)

## Escape hatches (emergency only)

| Env | Effect |
|-----|--------|
| `ASR_SKIP_DEPLOY_GUARD=1` | Skip entire guard |
| `ASR_DEPLOY_ALLOW_DIRTY=1` | Allow uncommitted files |
| `ASR_DEPLOY_ALLOW_SAME_VERSION=1` | Allow redeploy at same semver |

## Agent rule

`.cursor/rules/deploy-live-guard.mdc` (`alwaysApply: true`)

## Verify after deploy

```bash
python scripts/verify_live_status.py --expect 0.3.82 --require-azure-layout --min-pipeline rich-v20
curl -s "$ASR_CLOUD_RUN_URL/api/status" | jq '{version, deploy_git_sha}'
```
