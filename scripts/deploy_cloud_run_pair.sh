#!/usr/bin/env bash
# design/287 D4 + design/289 S2 — API then worker; resume worker if API already live.
# One Cloud Build; avoids parallel Conflict; survives gcloud crash after API revised.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
API_SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
API_URL="${ASR_CLOUD_RUN_URL:-https://asr-sentence-reading-984608876300.asia-northeast3.run.app}"

_local_ver="$(python -c "import re; from pathlib import Path; t=Path('src/sentence_reading/api/app.py').read_text(encoding='utf-8'); m=re.search(r'version=\"([^\"]+)\"', t); print(m.group(1) if m else '')")"
_head_sha="$(git rev-parse HEAD 2>/dev/null || true)"
_head12="${_head_sha:0:12}"

_live_matches_head() {
  # True when live version == local and deploy_git_sha prefix matches HEAD.
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

echo "design/287 D4 / 289 S2: API deploy (--source) …" >&2
unset ASR_DEPLOY_IMAGE || true
export ASR_CLOUD_RUN_SERVICE="$API_SERVICE"

set +e
bash scripts/deploy_cloud_run.sh "$@"
_api_rc=$?
set -e

if [[ "$_api_rc" -ne 0 ]]; then
  if _live_matches_head; then
    echo "warn: design/289 API deploy rc=${_api_rc} but live already at HEAD ${_head12} (${_local_ver}) — resume worker" >&2
  else
    echo "error: API deploy failed (rc=${_api_rc}) and live does not match HEAD" >&2
    exit "$_api_rc"
  fi
fi

IMG="$(gcloud run services describe "$API_SERVICE" \
  --region="$REGION" \
  --format='value(spec.template.spec.containers[0].image)')"
if [[ -z "$IMG" ]]; then
  echo "error: could not read API container image after deploy" >&2
  exit 1
fi
echo "design/287 D4: worker deploy --image $IMG (no second build) …" >&2
export ASR_DEPLOY_IMAGE="$IMG"
bash scripts/deploy_cloud_run_worker.sh "$@"

echo "design/287/289: pair deploy done (API source + worker image reuse)" >&2
