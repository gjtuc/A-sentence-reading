#!/usr/bin/env bash
# WHAT: Build+deploy A-sentence-reading gatekeeper to Cloud Run (remote build, no local Docker).
# WHY: PC-off access — design/25. Secrets via env flags; runtime SA = asr-tts.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
SA_EMAIL="${ASR_RUNTIME_SA:-asr-tts@${PROJECT_ID}.iam.gserviceaccount.com}"
BUCKET="${ASR_GCS_BUCKET:-asr-chaheon-warehouse}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI 가 없습니다. https://cloud.google.com/sdk/docs/install 후 다시 실행하세요." >&2
  exit 1
fi

: "${ASR_GOOGLE_CLIENT_ID:?Set ASR_GOOGLE_CLIENT_ID}"
: "${ASR_AUTH_SECRET:?Set ASR_AUTH_SECRET (strong random)}"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"

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
  --set-env-vars "ASR_GCS_BUCKET=${BUCKET},ASR_GCS_PREFIX=asr,ASR_EMAIL_AUTH=1,ASR_COOKIE_SECURE=1,ASR_GOOGLE_CLIENT_ID=${ASR_GOOGLE_CLIENT_ID},ASR_AUTH_SECRET=${ASR_AUTH_SECRET},GEMINI_API_KEY=${GEMINI_API_KEY},ASR_CLOUD_RUN_URL=https://asr-sentence-reading-984608876300.asia-northeast3.run.app"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Deployed: $URL"
echo "다음: Google OAuth 클라이언트에 JavaScript 원본 추가 → $URL"
echo "확인: curl -sS \"$URL/api/status\""
