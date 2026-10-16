# 403 — the phone app builds for the web (step 1 of the web version)

## Goal of this step

`flutter build web` succeeds and the page opens to the login screen without an
uncaught error. Nothing is hosted yet, and Android behaviour does not change.

The web version is built one step at a time:

1. Build and open without errors (this doc).
2. Host it on the same Cloud Run service under its own path, then web login.
3. Library and reading screen.
4. PDF upload from the browser file picker.
5. Native voice playback.
6. Shadowing (browser microphone).

The old server page (`src/sentence_reading/static`) stays untouched until the
new one does everything.

## What was in the way

- `mobile/web/` did not exist, and `mobile/.gitignore` excluded `web/` since the
  July scaffold. `flutter create --platforms=web .` added it. The same command
  also upgraded `pubspec.lock` and rewrote `.metadata`; both were reverted so the
  phone build keeps its exact packages.
- The code already compiled for the web. At runtime, the logged-out wipe
  (`LibraryController.clearAll`) called `path_provider`, which has no web
  implementation, twice: `_editStash.purgeAll()` and `_pdfHashCache.clearBound()`.
  The first throw also stopped the rest of the wipe. Both are now skipped when
  `kIsWeb`.
- `AuthDeepLinkBridge.start` asked the Android intent channel for a pending
  magic link. It now returns early on the web; step 2 reads the link from the
  page address instead.

## Tools

- `scripts/flutter_any.cmd ARGS` runs any flutter command in `mobile/` with the
  design/299 `ProgramFiles(x86)` fix.
- `scripts/web_probe.py` serves `mobile/build/web` on 127.0.0.1, opens it in a
  headless Chrome over DevTools, waits in real time, and writes
  `.cache/web_probe.png` and `.cache/web_probe.console.txt`. Uncaught errors
  include the Dart error text (`dart: ...`).
- `click/03_web_build.bat` does both and writes `click/out/web_build.result.txt`.

## Expected noise

Opened from 127.0.0.1, every API call is blocked by CORS because the server only
answers its own origin. That ends when step 2 serves the page from the server.
The click summary counts CORS lines apart from real errors.

## Result

Login screen renders with Korean text; uncaught errors 0; other errors 0.

## Tests

`tests/test_design_403_web_build.py`.
