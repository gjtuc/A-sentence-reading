#!/usr/bin/env bash
# WHAT: Build+deploy A-sentence-reading gatekeeper to Cloud Run (remote build, no local Docker).
# WHY: PC-off access — design/25·32. Secrets via env flags; runtime SA = asr-tts.
# 불변: --set-env-vars 는 나열한 키로 덮어씀 → 카카오 키도 반드시 포함(있을 때).
# 다음에: GitHub Actions CD (vars.ASR_CD_READY=1 · ASR_CD_ENABLED=1).
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
REGION="${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
SERVICE="${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
SA_EMAIL="${ASR_RUNTIME_SA:-asr-tts@${PROJECT_ID}.iam.gserviceaccount.com}"
BUCKET="${ASR_GCS_BUCKET:-asr-chaheon-warehouse}"
CLOUD_URL="${ASR_CLOUD_RUN_URL:-https://asr-sentence-reading-984608876300.asia-northeast3.run.app}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ASR_GOOGLE_CLIENT_ID:?Set ASR_GOOGLE_CLIENT_ID}"
: "${ASR_AUTH_SECRET:?Set ASR_AUTH_SECRET (strong random)}"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"

KAKAO_REST="${ASR_KAKAO_REST_API_KEY:-}"
KAKAO_SECRET="${ASR_KAKAO_CLIENT_SECRET:-}"
ADMIN_EMAILS="${ASR_ADMIN_EMAILS:-}"
# WHY: no hardcoded admin email in git (PII/ops). Empty => nobody is admin (fail-closed mint).
# EDGE: CD must set GitHub secret ASR_ADMIN_EMAILS; local deploy must export it.
_admin_n=0
if [[ -n "$ADMIN_EMAILS" ]]; then
  # WHY: count commas+1 without printing addresses (no tr newline portability issues).
  _admin_n=$(awk -F',' '{print NF}' <<<"$ADMIN_EMAILS")
fi
echo "ASR_ADMIN_EMAILS configured_count=${_admin_n} (values not printed)"

# WHY: CI·로컬에서 gcloud/권한 없이 계약만 검증 (design/32).
if [[ "${ASR_CD_DRY_RUN:-}" == "1" ]]; then
  kakao_state="off"
  if [[ -n "$KAKAO_REST" && -n "$KAKAO_SECRET" ]]; then
    kakao_state="on"
  elif [[ -n "$KAKAO_REST" || -n "$KAKAO_SECRET" ]]; then
    kakao_state="partial"
  fi
  echo "dry-run: would deploy service=${SERVICE} region=${REGION} project=${PROJECT_ID} sa=${SA_EMAIL} bucket=${BUCKET} kakao=${kakao_state}"
  if [[ "$kakao_state" == "partial" ]]; then
    echo "dry-run-warn: set both ASR_KAKAO_REST_API_KEY and ASR_KAKAO_CLIENT_SECRET (or neither)" >&2
    exit 2
  fi
  # design/86 — same partial-guard as real deploy (no secret values printed).
  smtp_host="${ASR_SMTP_HOST:-}"
  smtp_from="${ASR_SMTP_FROM:-}"
  smtp_state="off"
  if [[ -n "$smtp_host" && -n "$smtp_from" ]]; then
    smtp_state="on"
  elif [[ -n "$smtp_host" || -n "$smtp_from" || -n "${ASR_SMTP_USER:-}" || -n "${ASR_SMTP_PASS:-}" ]]; then
    smtp_state="partial"
  fi
  echo "dry-run: smtp=${smtp_state}"
  if [[ "$smtp_state" == "partial" ]]; then
    echo "dry-run-warn: set both ASR_SMTP_HOST and ASR_SMTP_FROM (or neither)" >&2
    exit 2
  fi
  exit 0
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI 가 없습니다. https://cloud.google.com/sdk/docs/install 후 다시 실행하세요." >&2
  exit 1
fi

# WHY: 값에 쉼표·특수문자 있어도 안전 — --set-env-vars 한 줄보다 env-vars-file.
ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/asr-run-env.XXXXXX.yaml")"
cleanup() { rm -f "$ENV_FILE"; }
trap cleanup EXIT

{
  echo "ASR_GCS_BUCKET: \"${BUCKET}\""
  echo "ASR_GCS_PREFIX: \"asr\""
  echo "ASR_EMAIL_AUTH: \"1\""
  echo "ASR_COOKIE_SECURE: \"1\""
  echo "ASR_GOOGLE_CLIENT_ID: \"${ASR_GOOGLE_CLIENT_ID}\""
  echo "ASR_AUTH_SECRET: \"${ASR_AUTH_SECRET}\""
  echo "GEMINI_API_KEY: \"${GEMINI_API_KEY}\""
  echo "ASR_CLOUD_RUN_URL: \"${CLOUD_URL}\""
  echo "ASR_ADMIN_EMAILS: \"${ADMIN_EMAILS}\""
  # design/79·80 — shadowing kill (unset/0=off). CD sets via vars.ASR_SHADOWING_PRACTICE.
  echo "ASR_SHADOWING_PRACTICE: \"${ASR_SHADOWING_PRACTICE:-0}\""
  # design/83 — login-required (unset/1=on). Kill with ASR_LOGIN_REQUIRED=0.
  echo "ASR_LOGIN_REQUIRED: \"${ASR_LOGIN_REQUIRED:-1}\""
  if [[ -n "$KAKAO_REST" && -n "$KAKAO_SECRET" ]]; then
    echo "ASR_KAKAO_REST_API_KEY: \"${KAKAO_REST}\""
    echo "ASR_KAKAO_CLIENT_SECRET: \"${KAKAO_SECRET}\""
  elif [[ -n "$KAKAO_REST" || -n "$KAKAO_SECRET" ]]; then
    echo "Kakao: set BOTH ASR_KAKAO_REST_API_KEY and ASR_KAKAO_CLIENT_SECRET (client secret is ON in console)." >&2
    exit 2
  fi
  # design/86 — optional SMTP for magic-link mail. host+from required together.
  SMTP_HOST="${ASR_SMTP_HOST:-}"
  SMTP_FROM="${ASR_SMTP_FROM:-}"
  SMTP_USER="${ASR_SMTP_USER:-}"
  SMTP_PASS="${ASR_SMTP_PASS:-}"
  SMTP_PORT="${ASR_SMTP_PORT:-}"
  SMTP_SSL="${ASR_SMTP_SSL:-}"
  SMTP_USER_SECRET="${ASR_SMTP_USER_SECRET:-st-auth-smtp-user}"
  SMTP_PASS_SECRET="${ASR_SMTP_PASSWORD_SECRET:-st-auth-smtp-password}"
  SMTP_SECRETS_MODE=""
  if [[ -n "$SMTP_HOST" && -n "$SMTP_FROM" ]]; then
    echo "ASR_SMTP_HOST: \"${SMTP_HOST}\""
    echo "ASR_SMTP_FROM: \"${SMTP_FROM}\""
    if [[ -n "$SMTP_PORT" ]]; then
      echo "ASR_SMTP_PORT: \"${SMTP_PORT}\""
    fi
    if [[ -n "$SMTP_SSL" ]]; then
      echo "ASR_SMTP_SSL: \"${SMTP_SSL}\""
    fi
    if [[ -n "$SMTP_USER" && -n "$SMTP_PASS" ]]; then
      echo "ASR_SMTP_USER: \"${SMTP_USER}\""
      echo "ASR_SMTP_PASS: \"${SMTP_PASS}\""
      SMTP_SECRETS_MODE="plain"
      echo "SMTP: configured (plain USER/PASS in env-vars-file; values not printed)" >&2
    else
      # WHY: Trading Naver mailbox already in Secret Manager — CD can omit USER/PASS.
      SMTP_SECRETS_MODE="secretmanager"
      echo "SMTP: configured (USER/PASS via Secret Manager ${SMTP_USER_SECRET}/${SMTP_PASS_SECRET})" >&2
    fi
  elif [[ -n "$SMTP_HOST" || -n "$SMTP_FROM" || -n "$SMTP_USER" || -n "$SMTP_PASS" ]]; then
    # FAIL-CLOSED: partial SMTP would look ready but cannot send.
    echo "SMTP: set BOTH ASR_SMTP_HOST and ASR_SMTP_FROM (or neither)." >&2
    exit 2
  fi
} >"$ENV_FILE"

gcloud config set project "$PROJECT_ID"

# WHY: CD SA 는 API enable 권한이 없을 수 있음 — 이미 켜진 프로젝트에서는 생략.
# 로컬 최초 배포만 ASR_ENABLE_APIS=1 로 강제.
if [[ "${ASR_ENABLE_APIS:-}" == "1" ]]; then
  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    texttospeech.googleapis.com \
    storage.googleapis.com \
    cloudresourcemanager.googleapis.com
elif [[ -n "${GITHUB_ACTIONS:-}" || "${ASR_CD_SKIP_API_ENABLE:-}" == "1" ]]; then
  echo "skip gcloud services enable (CI/CD — APIs assumed enabled)"
else
  # 로컬 수동: 실패해도 배포 시도 (이미 enable 된 경우 흔함)
  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    texttospeech.googleapis.com \
    storage.googleapis.com \
    cloudresourcemanager.googleapis.com \
    || echo "warn: services enable failed (continuing)" >&2
fi

# WHY: --source 는 Cloud Build 가 Dockerfile 로 원격 빌드 (로컬 Docker 불필요)
# SMTP Secret Manager: env-vars-file 만으로는 USER/PASS 참조가 빠지므로 --set-secrets 재부착.
DEPLOY_ARGS=(
  run deploy "$SERVICE"
  --source .
  --region "$REGION"
  --platform managed
  --allow-unauthenticated
  --service-account "$SA_EMAIL"
  --memory 1Gi
  --cpu 1
  --min-instances "${ASR_MIN_INSTANCES:-1}"
  --max-instances 3
  --timeout 300
  --env-vars-file "$ENV_FILE"
)
if [[ "${SMTP_SECRETS_MODE:-}" == "secretmanager" ]]; then
  DEPLOY_ARGS+=(--set-secrets="ASR_SMTP_USER=${SMTP_USER_SECRET:-st-auth-smtp-user}:latest,ASR_SMTP_PASS=${SMTP_PASS_SECRET:-st-auth-smtp-password}:latest")
fi
gcloud "${DEPLOY_ARGS[@]}"

URL="${ASR_CLOUD_RUN_URL:-}"
if [[ -z "$URL" ]]; then
  URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
fi
echo
echo "Deployed: $URL"
echo "다음: Google OAuth 클라이언트에 JavaScript 원본 추가 → $URL"
echo "확인: python scripts/verify_live_status.py --expect 0.2.34"
