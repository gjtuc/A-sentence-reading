#!/usr/bin/env bash
# WHAT: Build+deploy A-sentence-reading gatekeeper to Cloud Run (remote build, no local Docker).
# WHY: PC-off access — design/25·32. Secrets via env flags; runtime SA = asr-tts.
# 다음에: GitHub Actions CD (vars.ASR_CD_ENABLED=1) 가 이 스크립트를 호출.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
SA_EMAIL="${ASR_RUNTIME_SA:-asr-tts@${PROJECT_ID}.iam.gserviceaccount.com}"
BUCKET="${ASR_GCS_BUCKET:-asr-chaheon-warehouse}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ASR_GOOGLE_CLIENT_ID:?Set ASR_GOOGLE_CLIENT_ID}"
: "${ASR_AUTH_SECRET:?Set ASR_AUTH_SECRET (strong random)}"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"

# WHY: CI·로컬에서 gcloud/권한 없이 계약만 검증 (design/32).
if [[ "${ASR_CD_DRY_RUN:-}" == "1" ]]; then
  echo "dry-run: would deploy service=${SERVICE} region=${REGION} project=${PROJECT_ID} sa=${SA_EMAIL} bucket=${BUCKET}"
  exit 0
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI 가 없습니다. https://cloud.google.com/sdk/docs/install 후 다시 실행하세요." >&2
  exit 1
fi

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  texttospeech.googleapis.com \
  storage.googleapis.com

# WHY: --source 는 Cloud Build 가 Dockerfile 로 원격 빌드 (로컬 Docker 불필요)
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "$SA_EMAIL" \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 300 \
  --set-env-vars "ASR_GCS_BUCKET=${BUCKET},ASR_GCS_PREFIX=asr,ASR_EMAIL_AUTH=1,ASR_COOKIE_SECURE=1,ASR_GOOGLE_CLIENT_ID=${ASR_GOOGLE_CLIENT_ID},ASR_AUTH_SECRET=${ASR_AUTH_SECRET},GEMINI_API_KEY=${GEMINI_API_KEY},ASR_CLOUD_RUN_URL=https://asr-sentence-reading-984608876300.asia-northeast3.run.app,ASR_ADMIN_EMAILS=${ASR_ADMIN_EMAILS:-kimcha0809@gmail.com}"

URL="${ASR_CLOUD_RUN_URL:-}"
if [[ -z "$URL" ]]; then
  URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
fi
echo
echo "Deployed: $URL"
echo "다음: Google OAuth 클라이언트에 JavaScript 원본 추가 → $URL"
echo "확인: python scripts/verify_live_status.py --expect 0.2.33"
