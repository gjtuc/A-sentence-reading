#!/usr/bin/env bash
# design/287 D4 + 289 S2 + 290 P1 — API then worker; settle+recheck; always finish worker.
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
ok = (ver == want_ver) and (bool(head12) and sha.startswith(head12))
print(f"live_version={ver} live_sha={sha[:12]} want={want_ver} head12={head12} match={int(ok)}")
sys.exit(0 if ok else 1)
PY
}

_service_image() {
  local svc="$1"
  gcloud run services describe "$svc" --region="$REGION" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true
}

_log "design/290: pair start ver=${_local_ver} head12=${_head12}"

# --- Phase A: API ---
_log "phase=a start api_source"
unset ASR_DEPLOY_IMAGE || true
export ASR_CLOUD_RUN_SERVICE="$API_SERVICE"

set +e
bash scripts/deploy_cloud_run.sh "$@"
_api_rc=$?
set -e
_log "phase=a rc=${_api_rc}"

_api_ok=0
if [[ "$_api_rc" -eq 0 ]]; then
  _api_ok=1
elif _live_matches_head; then
  _log "warn: design/290 API rc=${_api_rc} but live already HEAD — continue"
  _api_ok=1
else
  _log "design/290: settle ${SETTLE_SEC}s then recheck live (gcloud may have revised despite crash)"
  sleep "$SETTLE_SEC"
  if _live_matches_head; then
    _log "warn: design/290 live matched after settle — continue worker"
    _api_ok=1
  fi
fi

if [[ "$_api_ok" -ne 1 ]]; then
  _log "error: phase=a failed and live does not match HEAD"
  exit "${_api_rc:-1}"
fi

IMG="$(_service_image "$API_SERVICE")"
if [[ -z "$IMG" ]]; then
  _log "error: could not read API container image"
  exit 1
fi
_log "phase=a image=${IMG}"

# --- Phase B: worker (always when phase A ok / live match) ---
_log "phase=b start worker_image"
export ASR_DEPLOY_IMAGE="$IMG"
set +e
bash scripts/deploy_cloud_run_worker.sh "$@"
_worker_rc=$?
set -e
_log "phase=b rc=${_worker_rc}"
if [[ "$_worker_rc" -ne 0 ]]; then
  _log "error: phase=b worker deploy failed"
  exit "$_worker_rc"
fi

# --- Phase C: image equality ---
WIMG="$(_service_image "$WORKER_SERVICE")"
_log "phase=c api_image=${IMG}"
_log "phase=c worker_image=${WIMG}"
if [[ -z "$WIMG" || "$WIMG" != "$IMG" ]]; then
  _log "error: API/worker image mismatch"
  exit 1
fi

_log "pair_ok=1 design/287/289/290 pair deploy done"
echo "design/290: pair_ok=1 (API+worker same image)" >&2
exit 0
