#!/usr/bin/env bash
# WHAT: gc_automation.env (+ 배포 SA JSON) → GitHub Actions Secrets/Variables.
# WHY: CD 켜기 전 Secrets 채움 (design/32). 값은 stdout에 찍지 않음.
# 사용:
#   bash scripts/sync_github_cd_secrets.sh
#   bash scripts/sync_github_cd_secrets.sh --enable
#   ASR_CD_DRY_RUN=1 bash scripts/sync_github_cd_secrets.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ASR_ENV_FILE:-/c/Users/user/Desktop/.cursor/gc_automation.env}"
SA_JSON="${ASR_CD_SA_JSON:-/c/Users/user/Desktop/.cursor/secrets/asr-github-deploy.json}"
ENABLE=0
for a in "$@"; do
  case "$a" in
    --enable) ENABLE=1 ;;
    --help|-h)
      echo "usage: $0 [--enable]"
      exit 0
      ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

need() {
  local n="$1"
  local v
  eval "v=\${$n-}"
  if [[ -z "$v" ]]; then
    echo "missing env: $n" >&2
    return 1
  fi
  echo "ok $n len=${#v}"
}

# edge: dry-run — gh 호출 없이 길이만
if [[ "${ASR_CD_DRY_RUN:-}" == "1" ]]; then
  need ASR_GOOGLE_CLIENT_ID
  need ASR_AUTH_SECRET
  need GEMINI_API_KEY
  need ASR_KAKAO_REST_API_KEY
  need ASR_KAKAO_CLIENT_SECRET
  if [[ -f "$SA_JSON" ]]; then
    echo "ok SA_JSON path_exists size=$(wc -c <"$SA_JSON" | tr -d ' ')"
  else
    echo "missing SA_JSON: $SA_JSON" >&2
    exit 2
  fi
  echo "dry-run: would set secrets + vars (enable=$ENABLE)"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI required" >&2
  exit 1
fi

need ASR_GOOGLE_CLIENT_ID
need ASR_AUTH_SECRET
need GEMINI_API_KEY
need ASR_KAKAO_REST_API_KEY
need ASR_KAKAO_CLIENT_SECRET

if [[ ! -f "$SA_JSON" ]]; then
  echo "missing deploy SA JSON: $SA_JSON" >&2
  echo "Create with scripts/ensure_github_deploy_sa.sh first." >&2
  exit 2
fi

# WHY: --body 는 셸 히스토리에 남을 수 있어 stdin 사용
printf '%s' "$ASR_GOOGLE_CLIENT_ID" | gh secret set ASR_GOOGLE_CLIENT_ID
printf '%s' "$ASR_AUTH_SECRET" | gh secret set ASR_AUTH_SECRET
printf '%s' "$GEMINI_API_KEY" | gh secret set GEMINI_API_KEY
printf '%s' "$ASR_KAKAO_REST_API_KEY" | gh secret set ASR_KAKAO_REST_API_KEY
printf '%s' "$ASR_KAKAO_CLIENT_SECRET" | gh secret set ASR_KAKAO_CLIENT_SECRET
if [[ -n "${ASR_ADMIN_EMAILS:-}" ]]; then
  printf '%s' "$ASR_ADMIN_EMAILS" | gh secret set ASR_ADMIN_EMAILS
  echo "ok ASR_ADMIN_EMAILS set"
fi
# design/86 — optional SMTP (only when both host+from present in env file).
if [[ -n "${ASR_SMTP_HOST:-}" && -n "${ASR_SMTP_FROM:-}" ]]; then
  printf '%s' "$ASR_SMTP_HOST" | gh secret set ASR_SMTP_HOST
  printf '%s' "$ASR_SMTP_FROM" | gh secret set ASR_SMTP_FROM
  echo "ok ASR_SMTP_HOST+FROM set"
  if [[ -n "${ASR_SMTP_USER:-}" ]]; then
    printf '%s' "$ASR_SMTP_USER" | gh secret set ASR_SMTP_USER
    echo "ok ASR_SMTP_USER set"
  fi
  if [[ -n "${ASR_SMTP_PASS:-}" ]]; then
    printf '%s' "$ASR_SMTP_PASS" | gh secret set ASR_SMTP_PASS
    echo "ok ASR_SMTP_PASS set"
  fi
  if [[ -n "${ASR_SMTP_PORT:-}" ]]; then
    printf '%s' "$ASR_SMTP_PORT" | gh secret set ASR_SMTP_PORT
    echo "ok ASR_SMTP_PORT set"
  fi
  if [[ -n "${ASR_SMTP_SSL:-}" ]]; then
    printf '%s' "$ASR_SMTP_SSL" | gh secret set ASR_SMTP_SSL
    echo "ok ASR_SMTP_SSL set"
  fi
elif [[ -n "${ASR_SMTP_HOST:-}" || -n "${ASR_SMTP_FROM:-}" || -n "${ASR_SMTP_USER:-}" || -n "${ASR_SMTP_PASS:-}" ]]; then
  echo "SMTP partial in env file: set BOTH ASR_SMTP_HOST and ASR_SMTP_FROM (or neither)." >&2
  exit 2
else
  echo "skip SMTP secrets (ASR_SMTP_HOST/FROM not in env file)"
fi
if [[ -n "${AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT:-}" && -n "${AZURE_DOCUMENT_INTELLIGENCE_KEY:-}" ]]; then
  printf '%s' "$AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT" | gh secret set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
  printf '%s' "$AZURE_DOCUMENT_INTELLIGENCE_KEY" | gh secret set AZURE_DOCUMENT_INTELLIGENCE_KEY
  echo "ok AZURE_DOCUMENT_INTELLIGENCE_* set"
elif [[ -n "${AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT:-}" || -n "${AZURE_DOCUMENT_INTELLIGENCE_KEY:-}" ]]; then
  echo "Azure DI partial in env file: set BOTH endpoint and key (or neither)." >&2
  exit 2
else
  echo "skip Azure DI secrets (not in env file)"
fi
gh secret set GCP_SA_KEY <"$SA_JSON"
echo "ok GCP_SA_KEY set from file"

gh variable set GCP_PROJECT_ID --body "${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
gh variable set ASR_CLOUD_RUN_REGION --body "${ASR_CLOUD_RUN_REGION:-asia-northeast3}"
gh variable set ASR_CLOUD_RUN_SERVICE --body "${ASR_CLOUD_RUN_SERVICE:-asr-sentence-reading}"
gh variable set ASR_GCS_BUCKET --body "${ASR_GCS_BUCKET:-asr-chaheon-warehouse}"
gh variable set ASR_CLOUD_RUN_URL --body "${ASR_CLOUD_RUN_URL:-https://asr-sentence-reading-984608876300.asia-northeast3.run.app}"

if [[ "$ENABLE" -eq 1 ]]; then
  gh variable set ASR_CD_ENABLED --body "1"
  echo "ok ASR_CD_ENABLED=1"
else
  echo "skip enable (pass --enable to set ASR_CD_ENABLED=1)"
fi

echo "done. next: python scripts/check_github_cd_ready.py"
