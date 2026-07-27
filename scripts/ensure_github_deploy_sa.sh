#!/usr/bin/env bash
# WHAT: GitHub Actions 배포용 SA + JSON 키 생성 (로컬 secrets/ 에만 저장).
# WHY: GCP_SA_KEY — 런타임 asr-tts 와 분리 (design/32).
# 불변: JSON 을 repo 에 커밋하지 않음.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
SA_ID="${ASR_CD_SA_ID:-asr-github-deploy}"
SA_EMAIL="${SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="${ASR_RUNTIME_SA:-asr-tts@${PROJECT_ID}.iam.gserviceaccount.com}"
OUT_JSON="${ASR_CD_SA_JSON:-/c/Users/user/Desktop/.cursor/secrets/asr-github-deploy.json}"

if [[ "${ASR_CD_DRY_RUN:-}" == "1" ]]; then
  echo "dry-run: would ensure SA=${SA_EMAIL} out=${OUT_JSON}"
  exit 0
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud required" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_JSON")"

if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "ok SA exists: $SA_EMAIL"
else
  gcloud iam service-accounts create "$SA_ID" \
    --project="$PROJECT_ID" \
    --display-name="ASR GitHub Actions deploy"
  echo "ok SA created: $SA_EMAIL"
fi

# 최소 배포 역할
for role in \
  roles/run.admin \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.writer \
  roles/storage.admin \
  roles/serviceusage.serviceUsageConsumer \
  roles/iam.serviceAccountUser
do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
  echo "ok role $role"
done

# 런타임 SA 로 배포하려면 actAs
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null || true

if [[ -f "$OUT_JSON" ]]; then
  echo "ok key file already present (not rotated): $OUT_JSON"
else
  gcloud iam service-accounts keys create "$OUT_JSON" \
    --iam-account="$SA_EMAIL" \
    --project="$PROJECT_ID"
  echo "ok key written (keep private)"
fi

echo "next: bash scripts/sync_github_cd_secrets.sh --enable"
