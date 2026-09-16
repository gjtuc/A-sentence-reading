# 300 — APK hang release

Version: **0.3.293** · Status: **locked**  
Amends [298](298-apk-commit-launch.md) · [289](289-ship-path-hardening.md)

## Why

0.3.292 cloud pair was smooth. APK was not.

- `kernel_snapshot` wrote `BUILD FAILED`, then `flutter` did not exit, so the design/298 retry never started.
- The retry called `gradlew --stop` and the new daemon disappeared.
- A later build wrote `app-release.apk` and then hung. design/289 only accepts that file after the process exits.

## Rules

1. If the APK log stays idle after `BUILD FAILED`, `kernel_snapshot_program`, or `compileFlutterBuildRelease`, stop that process tree. Then the existing one retry can run.
2. `gradlew --stop` must finish, and no `GradleDaemon` process may remain, before the next `flutter build apk`.
3. If `app-release.apk` is newer than the build start and its size stays stable, stop the hung flutter and treat the file as success.

## Non-goals

- Cloud Run behavior
- Version bump

## Acceptance

`tests/test_design_300_apk_hang_release.py`
