#!/usr/bin/env bash
# design/173c — deploy ingest worker (same image, ASR_SERVICE_ROLE=worker).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ASR_WORKER_SECRET:?Set ASR_WORKER_SECRET (shared with API ASR_WORKER_SECRET)}"

export ASR_CLOUD_RUN_SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading-worker}"
export ASR_SERVICE_ROLE=worker
export ASR_INGEST_INLINE=1
export ASR_MIN_INSTANCES="${ASR_WORKER_MIN_INSTANCES:-0}"
export ASR_MAX_INSTANCES="${ASR_WORKER_MAX_INSTANCES:-4}"
export ASR_CLOUD_RUN_CONCURRENCY="${ASR_WORKER_CONCURRENCY:-2}"
export ASR_CLOUD_RUN_MEMORY="${ASR_WORKER_MEMORY:-2Gi}"
export ASR_CLOUD_RUN_CPU="${ASR_WORKER_CPU:-2}"
export ASR_DEPLOY_ALLOW_SAME_VERSION=1
export ASR_SKIP_POST_DEPLOY_VERIFY=1

bash scripts/deploy_cloud_run.sh "$@"

REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
PROJECT_ID="${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
SERVICE="${ASR_CLOUD_RUN_SERVICE}"
WORKER_URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)' 2>/dev/null || true)"
echo
echo "Worker URL: ${WORKER_URL:-unknown}"
echo "Next on API service: ASR_WORKER_URL + ASR_WORKER_SECRET, then ASR_INGEST_INLINE=0"
