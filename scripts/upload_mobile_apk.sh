#!/usr/bin/env bash
# design/161 — upload release APK to GCS public object for settings download.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-peaceful-basis-503207-t4}"
BUCKET="${ASR_GCS_BUCKET:-asr-chaheon-warehouse}"
PREFIX="${ASR_GCS_PREFIX:-asr}"
OBJECT="${PREFIX}/mobile/sentence-reading-latest.apk"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK="${1:-$ROOT/mobile/build/app/outputs/flutter-apk/app-release.apk}"

if [[ ! -f "$APK" ]]; then
  echo "APK not found: $APK" >&2
  echo "Run: cd mobile && flutter build apk --release" >&2
  exit 1
fi

if ! command -v gsutil >/dev/null 2>&1; then
  echo "gsutil required (Google Cloud SDK)." >&2
  exit 1
fi

gcloud config set project "$PROJECT_ID" >/dev/null
URI="gs://${BUCKET}/${OBJECT}"
gsutil cp "$APK" "$URI"
gsutil acl ch -u AllUsers:R "$URI" 2>/dev/null || true
PUBLIC_URL="https://storage.googleapis.com/${BUCKET}/${OBJECT}"
echo "uploaded: $URI"
echo "public:   $PUBLIC_URL"
echo "export ASR_MOBILE_APK_URL=\"$PUBLIC_URL\""
