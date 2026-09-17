#!/usr/bin/env bash
# design/287 D4 + 289/290/291 — API then worker; staged source; settle; finish worker.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
API_SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
WORKER_SERVICE="${ASR_WORKER_CLOUD_RUN_SERVICE:-asr-sentence-reading-worker}"
API_URL="${ASR_CLOUD_RUN_URL:-https://asr-sentence-reading-984608876300.asia-northeast3.run.app}"
SETTLE_SEC="${ASR_PAIR_SETTLE_SEC:-20}"
PAIR_LOG="${ROOT}/.tmp_pair_deploy.log"
: >"$PAIR_LOG"

_local_ver="$(python -c "import re; from pathlib import Path; t=Path('src/sentence_reading/api/app.py').read_text(encoding='utf-8'); m=re.search(r'version=\"([^\"]+)\"', t); print(m.group(1) if m else '')")"
_head_sha="$(git rev-parse HEAD 2>/dev/null || true)"
_head12="${_head_sha:0:12}"

_log() { echo "$*" | tee -a "$PAIR_LOG" >&2; }

_live_matches_head() {
  python - "$API_URL" "$_local_ver" "$_head12" <<'PY'
import json, sys, urllib.request
url, want_ver, head12 = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with urllib.request.urlopen(url.rstrip("/") + "/api/status", timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", errors="replace"))
except Exception as e:
    print(f"live_check_fail:{e}", file=sys.stderr)
    sys.exit(1)
ver = str(d.get("version") or "")
sha = str(d.get("deploy_git_sha") or d.get("git_sha") or "")
sha_ok = bool(head12) and sha.startswith(head12)
ver_ok = ver == want_ver and bool(want_ver)
ok = ver_ok and (sha_ok or bool(sha))
print(f"live_version={ver} live_sha={sha[:12]} want={want_ver} head12={head12} sha_ok={int(sha_ok)} match={int(ok)}")
sys.exit(0 if ok else 1)
PY
}

_service_image() {
  local svc="$1"
  gcloud run services describe "$svc" --region="$REGION" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true
}

_log "design/291: pair start ver=${_local_ver} head12=${_head12}"

# --- Phase A: API (staged source by default) ---
_log "phase=a start api_source"
unset ASR_DEPLOY_IMAGE || true
export ASR_CLOUD_RUN_SERVICE="$API_SERVICE"

if [[ "${ASR_PAIR_STAGED_SOURCE:-1}" == "1" ]]; then
  STAGE="$(bash scripts/stage_git_archive_for_ship.sh)"
  export ASR_DEPLOY_SOURCE_DIR="$STAGE"
  _log "phase=a staged_source=${STAGE}"
else
  unset ASR_DEPLOY_SOURCE_DIR || true
  _log "phase=a worktree_source=. (ASR_PAIR_STAGED_SOURCE=0)"
fi

set +e
bash scripts/deploy_cloud_run.sh "$@"
_api_rc=$?
set -e
_log "phase=a rc=${_api_rc}"

_api_ok=0
if [[ "$_api_rc" -eq 0 ]]; then
  _api_ok=1
elif _live_matches_head; then
  _log "warn: design/290 API rc=${_api_rc} but live version matches — continue"
  _api_ok=1
else
  _log "design/290: settle ${SETTLE_SEC}s then recheck live"
  sleep "$SETTLE_SEC"
  if _live_matches_head; then
    _log "warn: design/290 live matched after settle — continue worker"
    _api_ok=1
  fi
fi

if [[ "$_api_ok" -ne 1 ]]; then
  _log "error: phase=a failed and live does not match"
  exit "${_api_rc:-1}"
fi

IMG="$(_service_image "$API_SERVICE")"
if [[ -z "$IMG" ]]; then
  _log "error: could not read API container image"
  exit 1
fi
_log "phase=a image=${IMG}"

# design/292 G2 — API must still be product API before worker hop.
set +e
python scripts/check_api_service_role.py --expect-version "$_local_ver"
_role_rc=$?
set -e
_log "phase=a api_role_check rc=${_role_rc}"
if [[ "$_role_rc" -ne 0 ]]; then
  _log "error: design/292 API role gate failed after phase A"
  exit "$_role_rc"
fi

# Worker must deploy from worktree scripts but reuse image (no second upload).
unset ASR_DEPLOY_SOURCE_DIR || true
unset ASR_CLOUD_RUN_SERVICE || true
unset ASR_SERVICE_ROLE || true

# --- Phase B: worker ---
_log "phase=b start worker_image"
export ASR_DEPLOY_IMAGE="$IMG"
export ASR_CLOUD_RUN_SERVICE="${ASR_WORKER_CLOUD_RUN_SERVICE:-asr-sentence-reading-worker}"
set +e
bash scripts/deploy_cloud_run_worker.sh "$@"
_worker_rc=$?
set -e
_log "phase=b rc=${_worker_rc}"
if [[ "$_worker_rc" -ne 0 ]]; then
  _log "error: phase=b worker deploy failed"
  exit "$_worker_rc"
fi

# --- Phase C: same digest, or worker-repo copy of this release ---
WIMG="$(_service_image "$WORKER_SERVICE")"
_log "phase=c api_image=${IMG}"
_log "phase=c worker_image=${WIMG}"
set +e
python scripts/check_api_worker_images_match.py --expect-version "$_local_ver"
_img_rc=$?
set -e
if [[ "$_img_rc" -ne 0 ]]; then
  _log "error: API/worker image digest mismatch"
  exit "$_img_rc"
fi

# design/292 — API must remain api after worker hop.
set +e
python scripts/check_api_service_role.py --expect-version "$_local_ver"
_role_rc=$?
set -e
_log "phase=c api_role_check rc=${_role_rc}"
if [[ "$_role_rc" -ne 0 ]]; then
  _log "error: design/292 API role gate failed after phase B"
  exit "$_role_rc"
fi

_log "pair_ok=1 design/292 pair deploy done"
echo "design/292: pair_ok=1 (API+worker same digest; API role ok)" >&2
exit 0
