# 402 — long jobs run on the local PC from a click file

## Why

Deploys, APK builds and full test runs take 5 to 20 minutes. When the agent waits
and checks on them, every check costs tokens. Instead the user double-clicks a
file, the PC runs the whole job, and the agent reads one short result file.

The stock project already does this in `D:\.cursor\scratch\lifecycle_ga\click\`.
ASR uses its own folder and runner so neither project can break the other.

## Layout

- `click/NN_name.bat` — one per job. Double-click to run.
- `click/_job.cmd` — opens a new window that stays open (`cmd /k`), then runs
  `click/_run.py JOB`.
- `click/_run.py` — runs the steps, writes everything to `click/out/JOB.log`
  and a short Korean summary to `click/out/JOB.result.txt`. The first line of the
  summary is `DONE` or `FAILED`.
- `click/known_failures.txt` — failures that predate a change. The tests job
  lists them separately from new failures.

`click/out/` is not committed. It is not called `logs/` because `.cursorignore`
hides every `logs/` folder from the agent's file reader.

## Jobs

| File | Job |
|---|---|
| `00_selftest.bat` | a few seconds; checks the window, log and result file |
| `01_tests.bat` | Python suite and Flutter suite |
| `02_ship_and_install.bat` | freshness guard, evidence floor, pre-deploy guard, ship, live verify, APK build, `adb install -r`, `versionName` check |

`02` stops at the first failure. It never pushes by itself (the ship script
does), never sets `ASR_SKIP_*`, and builds the APK only after live verify passes.
It installs only when exactly one phone answers `adb devices` (three tries).

## Safety

- One ASR job at a time: `click/out/.running` holds the pid. A second job
  refuses while that pid is alive.
- If a stock click job is running (a live `_tee.py` Python whose parent window
  is a `lifecycle_ga` click window), the job asks before starting, because both
  slow down and a Gradle build can stall.

## Agent rule

Start nothing long in the agent shell when a click job exists for it. Ask the
user to double-click the file, end the turn, and read only
`click/out/JOB.result.txt` when the user says it finished.

## Tests

`tests/test_design_402_click_runner.py`.
