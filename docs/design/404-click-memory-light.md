# 404 — click jobs wait for memory and size themselves to it

## Why

On 2026-10-16 the full test job finished while the stock simulation ran three
workers at 2.6–2.9 GB each. The PC had 1.4 GB free, the click window printed
"메모리 리소스가 부족하여 이 명령을 처리할 수 없습니다", and an APK build
(Gradle heap ceiling 8 GB in `mobile/android/gradle.properties`) would have
pushed it over.

## Rules

All in `click/_mem.py`, used by every `Job.run` in `click/_run.py`. A new job
gets the light by calling `job.run(..., step=...)`; there is no other way to
start a step.

- **Usable memory** is the smaller of free RAM and free commit, minus a 1 GB
  reserve for the desktop.
- **Traffic light.** Before a step starts it waits until usable memory covers the
  step's need. It checks every 15 s, writes a `[빨간불]` line every 5 minutes, and
  sets `click/out/JOB.result.txt` to "메모리 기다리는 중". It gives up after 8 hours.
  Nothing is asked of the user; the old stock y/n prompt is gone.
- **Need.** Each step has a floor (`MIN_NEED_GB`). The measured peak of the
  step's process tree is kept in `click/out/mem_history.json` (last 5). For fixed
  steps the need becomes 1.2 × the largest recent peak, never below the floor.
- **Knobs.** Two steps are sized to what is usable when they start:
  - Flutter tests: `--concurrency` = usable / 0.6 GB, 1 to the core count.
  - APK build: Gradle heap via `GRADLE_OPTS=-Dorg.gradle.jvmargs=-Xmx…`, usable
    − 1.5 GB, between 2 and 8 GB. Verified on this PC: the daemon started with the
    passed `-Xmx` instead of the 8 GB in `gradle.properties`. Idle Gradle daemons
    are killed before and after the build, since they hold their heap for hours.
- **Watch.** While a step runs, its peak and the machine's lowest free memory are
  logged. Below 0.4 GB free a `[주의]` line is written once.
- `step="none"` skips the light. Only the selftest uses it.

## What it cannot do

- Python tests and the web build (dart2js) have no memory knob. They only wait.
- Memory the stock workers already hold is not taken back. A step that starts
  can still be squeezed if the stock workers grow afterwards; design/406 pauses it.
- A hard cap (Windows job object) was rejected: a capped build fails instead of
  slowing down.

## Tests

`tests/test_design_404_memory_light.py`.
