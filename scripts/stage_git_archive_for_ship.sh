#!/usr/bin/env bash
# design/291 R1 — export HEAD into a clean stage dir for gcloud --source upload.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${ASR_SHIP_STAGE_DIR:-$ROOT/.tmp_ship_stage}"

rm -rf "$STAGE"
mkdir -p "$STAGE"
# Tracked tree only — avoids untracked locks and dirty uploads.
git -C "$ROOT" archive HEAD | tar -x -C "$STAGE"
echo "$STAGE"
