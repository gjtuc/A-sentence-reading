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

# design/293 F1 — encode the smooth-path checklist before pair.
echo "design/293 preflight checklist:" >&2
echo "  1. freshness + version bump above live" >&2
echo "  2. one version commit pushed to origin/main" >&2
echo "  3. no tracked dirty files" >&2
echo "  4. no parallel APK/flutter build" >&2
echo "  5. use ship_release only (staged pair + role gates)" >&2
echo "  6. APK only after ship_release OK" >&2
echo "  7. verify_live + api_role_ok" >&2
echo "  8. optional adb install" >&2

_tracked_dirty="$(git status --porcelain --untracked-files=no 2>/dev/null || true)"
if [[ -n "$_tracked_dirty" ]]; then
  echo "error: design/293 refuse ship — tracked working tree dirty:" >&2
  echo "$_tracked_dirty" >&2
  exit 2
fi

# design/303 — push a fast-forward before deploy. Refusing after the fact
# wasted a ship. Never force-push. Behind or diverged still stops.
_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
_head="$(git rev-parse HEAD 2>/dev/null || true)"
_origin="$(git rev-parse origin/main 2>/dev/null || true)"
if [[ "${ASR_SHIP_ALLOW_UNPUSHED:-0}" != "1" ]]; then
  if [[ "$_branch" != "main" ]]; then
    echo "error: design/303 refuse ship — branch is ${_branch:-unknown}, not main" >&2
    exit 2
  fi
  if [[ -z "$_head" || -z "$_origin" ]]; then
    echo "error: design/303 refuse ship — missing HEAD or origin/main" >&2
    exit 2
  fi
  if [[ "$_head" != "$_origin" ]]; then
    if git merge-base --is-ancestor "$_origin" "$_head"; then
      echo "design/303: push origin main before ship" >&2
      # design/305 — wrapper already pushed with Windows git.exe. Do not call MSYS git.
      if [[ "${ASR_SHIP_WINDOWS_PUSHED:-0}" == "1" ]]; then
        echo "error: design/305 Windows git push did not move origin/main" >&2
        exit 2
      fi
      _git_win="/c/Program Files/Git/cmd/git.exe"
      if [[ -f "$_git_win" ]]; then
        echo "design/305: Windows git.exe push" >&2
        "$_git_win" push origin main
      else
        git push origin main
      fi
      _origin="$(git rev-parse origin/main)"
      _head="$(git rev-parse HEAD)"
    fi
  fi
  if [[ "$_head" != "$_origin" ]]; then
    echo "error: design/303 refuse ship — HEAD ($_head) != origin/main ($_origin); pull --ff-only first (or ASR_SHIP_ALLOW_UNPUSHED=1)" >&2
    exit 2
  fi
fi

python - <<'PY'
from pathlib import Path
import re
import sys
root = Path(".")
app = re.search(r'version="([^"]+)"', (root / "src/sentence_reading/api/app.py").read_text(encoding="utf-8"))
pub = re.search(r"^version:\s*([0-9.]+)", (root / "mobile/pubspec.yaml").read_text(encoding="utf-8"), re.M)
cfg = re.search(r"kAppVersionLabel = '([^']+)'", (root / "mobile/lib/config.dart").read_text(encoding="utf-8"))
av = app.group(1) if app else ""
pv = pub.group(1) if pub else ""
cv = cfg.group(1) if cfg else ""
print(f"design/293 versions app={av} pubspec={pv} config={cv}", flush=True)
if not av or av != pv or av != cv:
    print("error: design/293 version mismatch across app/pubspec/config", file=sys.stderr)
    sys.exit(2)
PY

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

echo "design/292: check_api_service_role ..." >&2
python scripts/check_api_service_role.py --expect-version "$_local_ver"

# Prefer bash-available gcloud via PATH from env / Cloud SDK.
if command -v gcloud >/dev/null 2>&1; then
  python scripts/check_api_worker_images_match.py --expect-version "$_local_ver"
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

echo "design/292: ship_release OK" >&2
