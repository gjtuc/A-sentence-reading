# 298 — Windows commit launcher and APK snapshot retry

Version: **0.3.291** · Status: **locked**  
Amends [296](296-windows-commit-shell.md) · [291](291-ship-staged-source-bash-apk.md)

## Why

0.3.290 cloud ship was smooth. Commit and APK were not.

- `powershell -File scripts/git_commit.ps1` is blocked by the execution policy.
- APK invoked `flutter` from PowerShell, so Gradle stderr became `RemoteException` and the script died.
- `kernel_snapshot` / invalid depfile retry existed only for SameDrive cache. A second build overlapped a live `flutter build apk` and exited `-1073741510`.

## Rules

1. Commit with `scripts/git_commit.cmd`. It runs `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git_commit.ps1`.
2. `build_release_apk.ps1` runs `flutter build apk` via `cmd /c`. Success is exit code plus a fresh APK file, not stderr warnings.
3. If `flutter build apk` is already running, exit 2. Do not start another.
4. On `kernel_snapshot_program`, `compileFlutterBuildRelease`, or `Invalid depfile`, wipe `.dart_tool/flutter_build` and retry once on the default cache too.

## Non-goals

- Cloud Run behavior  
- Ops ship of the launcher and APK retry  

## Acceptance

`tests/test_design_298_apk_commit_launch.py`
