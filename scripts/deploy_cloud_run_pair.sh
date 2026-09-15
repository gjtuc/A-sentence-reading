#!/usr/bin/env bash
# design/287 D4 — sequential API then worker; worker reuses API image (one Cloud Build).
# Saves ~6–10 min vs two `gcloud run deploy --source` and avoids parallel Conflict.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
API_SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"

echo "design/287 D4: API deploy (--source) …" >&2
unset ASR_DEPLOY_IMAGE || true
# Ensure API service name for first hop (worker script overrides later).
export ASR_CLOUD_RUN_SERVICE="$API_SERVICE"
bash scripts/deploy_cloud_run.sh "$@"

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

echo "design/287 D4: pair deploy done (API source + worker image reuse)" >&2
