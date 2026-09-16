# 303 — Smooth ship launch

Version: **0.3.295** · Status: **locked**

## Why

The 0.3.294 ship was correct, but three launches failed before the product ran. Ship refused because HEAD was not on `origin/main` yet. `flutter build apk` exited `0x2371` because `ProgramFiles(x86)` was unset. Pytest collected the D: tests and imported the Desktop checkout.

## Rules

1. `scripts/ship_release.sh` pushes `origin main` when that ref is an ancestor of HEAD, then deploys. It does not force-push. If the histories diverged or local is behind, it stops and asks for `git pull --ff-only`.
2. `scripts/build_release_apk.ps1` sets `ProgramFiles(x86)` with `SetEnvironmentVariable` before `flutter build apk`. Do not write `$env:ProgramFiles(x86)`.
3. Python tests run via `scripts/pytest.cmd`. It sets the working directory and `PYTHONPATH` to this repo. `tests/conftest.py` drops any other `sentence_reading` checkout from `sys.path`.

## Non-goals

- Phone install when no device is attached
- A version bump for this launcher

## Acceptance

`tests/test_design_303_smooth_launch.py`
