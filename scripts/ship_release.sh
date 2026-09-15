#!/usr/bin/env bash
# design/291 R2 — bash SoT for cloud ship (+ optional APK after).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ASR_SHIP_ENV_FILE:-/c/Users/user/Desktop/.cursor/gc-home/gc_automation.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

_apk_running() {
  # Best-effort: Windows tasklist / Unix pgrep.
  if command -v tasklist >/dev/null 2>&1; then
    tasklist 2>/dev/null | grep -qiE 'flutter|dart' || return 1
    return 0
  fi
  pgrep -f 'build_release_apk|flutter build apk' >/dev/null 2>&1
}

if [[ -z "${ASR_SHIP_ALLOW_PARALLEL_APK:-}" ]] && _apk_running; then
  echo "design/291: refuse cloud ship while flutter/APK may be running (ASR_SHIP_ALLOW_PARALLEL_APK=1 to override)" >&2
  exit 2
fi

echo "design/291: deploy_cloud_run_pair.sh ..." >&2
bash scripts/deploy_cloud_run_pair.sh "$@"

if [[ "${ASR_SHIP_SKIP_VERIFY:-0}" == "1" ]]; then
  echo "design/291: ASR_SHIP_SKIP_VERIFY=1 — skip verify" >&2
  echo "design/291: ship_release OK" >&2
  exit 0
fi

_local_ver="$(python -c "import re; from pathlib import Path; t=Path('src/sentence_reading/api/app.py').read_text(encoding='utf-8'); m=re.search(r'version=\"([^\"]+)\"', t); print(m.group(1) if m else '')")"
echo "design/291: verify_live_status --expect ${_local_ver}" >&2
python scripts/verify_live_status.py --require-azure-layout --min-pipeline rich-v20 --expect "$_local_ver"

# Prefer bash-available gcloud via PATH from env / Cloud SDK.
if command -v gcloud >/dev/null 2>&1; then
  python scripts/check_api_worker_images_match.py
else
  echo "warn: gcloud not on PATH for image check — skip (pair already compared)" >&2
fi

if [[ "${WITH_APK:-0}" == "1" ]]; then
  echo "design/291: build_release_apk.ps1 ..." >&2
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_release_apk.ps1
  if [[ "${WITH_ADB_INSTALL:-0}" == "1" ]]; then
    APK="data/sentence-reading-latest.apk"
    ADB="${ANDROID_HOME:-$LOCALAPPDATA/Android/Sdk}/platform-tools/adb.exe"
    ADB="${ADB//\\//}"
    if [[ -x "$ADB" || -f "$ADB" ]]; then
      "$ADB" install -r "$APK"
    else
      echo "warn: adb not found; APK at $APK" >&2
    fi
  fi
fi

echo "design/291: ship_release OK" >&2
