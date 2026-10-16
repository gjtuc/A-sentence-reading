# 406 — Click jobs pause on red and resume on green while a step runs

## Problem

design/404 checked the light only before a step started. Once a step ran, a red
light only wrote a warning. The user meant a traffic light that keeps watching:
stop on red, wait, go on green, stop again on the next red, as often as needed.

A second gap showed up on 2026-10-16 15:31: the selftest window printed its red
line and then Windows wrote "메모리 리소스가 부족하여 이 명령을 처리할 수 없습니다".
The waiting Python itself died, so nothing was watching any more.

## What changed

- **Light during a step.** `Watch` looks every 2 s. When usable memory (free minus
  the 1 GB reserve) drops below 0 and a stock job is running, it suspends the whole
  process tree of the step (`psutil` suspend), plus Gradle and Kotlin daemons for
  the APK build, which run outside the tree. At 0.5 GB usable it resumes them.
  Processes started while paused are suspended too. Each pause and resume is a
  `[빨간불]` / `[초록불]` line, and the result lists how often and how long.
- **Which steps.** `PAUSABLE` is Python tests, Flutter tests, the web build and the
  APK build. The deploy, the phone install and the browser check are not paused:
  they run against network or wall-clock timeouts.
- **No stock job, no pause.** Suspending does not give memory back. Only the stock
  job can free it, so without one a pause would never end. The stock check runs at
  most once a minute; when the stock jobs end while a step is paused, it resumes.
- **Timeouts after a pause.** A suspended test's timers keep counting, so a test can
  time out right after resume. When a paused test step has new failures, it runs
  once more (`test_step`).
- **A dead window restarts.** `_job.cmd` runs the job again after 15 s when Python
  exits without writing `DONE` or `FAILED` and `click\out\JOB.restart_ok` exists, up
  to 20 times. `_run.py` writes the marker at start and removes it when the job
  ends and when the deploy step begins (running a deploy job again from the top is
  not safe). A `MemoryError` inside a job exits with code 75 for the same restart.
- **Leftovers.** The live process tree of a step is kept in `click\out\.step_procs`.
  The next run kills what a dead window left behind (suspended ones included),
  matching process start time so a reused PID is never touched. `Watch.stop`
  always resumes what it suspended.

- **White screen counted as success.** The first `03` run took its screenshot at a
  fixed 25 s, before Flutter had drawn anything, and reported 0 errors on a white
  page. `web_probe.py` now waits up to 90 s for the engine's `flutter-first-frame`
  event, listens 3 s more, then takes the screenshot. The click job fails on
  `NO-FIRST-FRAME`.

- **Wall-clock budget killed a paused build (0.3.444).** `build_release_apk.ps1` stopped
  flutter 25 min after it started. The light had paused the build 5 times (23 min), so
  the budget ran out mid-build. The script is suspended together with the build, so it
  now counts awake time only: each 5 s tick adds at most 15 s.
- **04 builds when needed.** `click\out\apk_version.txt` holds the app version of the
  last APK a click job built. `04_install.bat` builds first when it is not the app
  version, then installs. It never deploys.

## Tests

`tests/test_design_406_pause_resume.py` (one test really freezes and resumes a child
process). The restart loop was also run with a stub that crashes on the first try.
