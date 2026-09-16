# 299 — Windows flutter test launcher

Version: **0.3.292** · Status: **locked**  
Amends [298](298-apk-commit-launch.md)

## Why

Title-card and hydrate-reuse tests failed before they ran. The agent shell had no `ProgramFiles(x86)`, so `flutter test` exited on a missing Windows message (`0x2371`). The retry assigned `$env:'ProgramFiles(x86)'` and PowerShell aborted at parse time. `Set-Item` / `SetEnvironmentVariable` worked.

A mid-file test splice also left `path` undefined in the next function. That is an edit rule, not a product bug.

## Rules

1. Mobile tests run via `scripts/flutter_test.cmd`. It uses `ExecutionPolicy Bypass` and `SetEnvironmentVariable('ProgramFiles(x86)', ...)`.
2. Do not write `$env:ProgramFiles(x86)` or `$env:'ProgramFiles(x86)'`.
3. Do not run bare `flutter test` from an agent shell on this PC.
4. Add a new test at the end of the file. Do not insert it into an existing test function.

## Non-goals

- Cloud Run behavior
- Ops ship of the launcher

## Acceptance

`tests/test_design_299_flutter_test_launch.py`
