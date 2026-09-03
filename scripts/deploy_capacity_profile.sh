#!/usr/bin/env bash
# design/173 — capacity A/B profiles for subjective testing (one turn per deploy).
#
# Usage:
#   bash scripts/deploy_capacity_profile.sh turn0-baseline-off
#   bash scripts/deploy_capacity_profile.sh turn1-api-throttle-only
#   bash scripts/deploy_capacity_profile.sh turn2-current-173
#   bash scripts/deploy_capacity_profile.sh turn3-all-throttle-on
#
# Before each test: wait until Cloud Run scales to zero (turn0/1 min=0) or use fresh session.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROFILE="${1:-}"
if [[ -z "$PROFILE" ]]; then
  echo "usage: $0 <profile-name>" >&2
  echo "profiles: turn0-baseline-off turn1-api-throttle-only turn2-current-173 turn3-all-throttle-on" >&2
  exit 2
fi

PROFILE_FILE="$ROOT/scripts/capacity_profiles/${PROFILE}.env"
if [[ ! -f "$PROFILE_FILE" ]]; then
  echo "missing profile: $PROFILE_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$PROFILE_FILE"
set +a

export ASR_CAPACITY_PROFILE="${ASR_CAPACITY_PROFILE:-$PROFILE}"
if [[ "${CLEAR_WORKER_ENV:-}" == "1" ]]; then
  unset ASR_WORKER_URL ASR_WORKER_SECRET
fi
REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
API_SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
WORKER_SERVICE="${ASR_WORKER_SERVICE:-asr-sentence-reading-worker}"

echo "=== capacity profile: ${ASR_CAPACITY_PROFILE} ==="
cat "$PROFILE_FILE" | grep -v '^#' | grep -v '^$' || true

if [[ "${CLEAR_WORKER_ENV:-}" == "1" ]]; then
  echo "clearing API worker wake env (ASR_WORKER_URL, ASR_WORKER_SECRET)..."
  gcloud run services update "$API_SERVICE" \
    --region="$REGION" \
    --remove-env-vars=ASR_WORKER_URL,ASR_WORKER_SECRET \
    2>/dev/null || echo "warn: remove-env-vars skipped (may already absent)"
fi

bash scripts/deploy_cloud_run.sh

if [[ "${DEPLOY_WORKER:-}" == "1" ]]; then
  export ASR_CLOUD_RUN_SERVICE="$WORKER_SERVICE"
  export ASR_SERVICE_ROLE=worker
  export ASR_INGEST_INLINE=1
  export ASR_MIN_INSTANCES="${ASR_WORKER_MIN_INSTANCES:-0}"
  export ASR_MAX_INSTANCES="${ASR_WORKER_MAX_INSTANCES:-4}"
  export ASR_CLOUD_RUN_CONCURRENCY="${ASR_WORKER_CONCURRENCY:-2}"
  export ASR_CLOUD_RUN_MEMORY="${ASR_WORKER_MEMORY:-2Gi}"
  export ASR_CLOUD_RUN_CPU="${ASR_WORKER_CPU:-2}"
  export ASR_CPU_THROTTLING="${ASR_WORKER_CPU_THROTTLING:-0}"
  export ASR_DEPLOY_ALLOW_SAME_VERSION=1
  export ASR_SKIP_POST_DEPLOY_VERIFY=1
  bash scripts/deploy_cloud_run.sh
elif [[ "${SCALE_WORKER_MIN:-}" == "0" ]]; then
  echo "scaling worker min=0 (idle; API uses inline ingest)..."
  gcloud run services update "$WORKER_SERVICE" \
    --region="$REGION" \
    --min-instances=0 \
    2>/dev/null || echo "warn: worker scale skipped (service may not exist)"
fi

echo
echo "Live profile: ${ASR_CAPACITY_PROFILE}"
echo "Check: curl -s \$ASR_CLOUD_RUN_URL/api/status | jq .capacity_profile,.ingest_inline,.access_gate_ttl_s"
