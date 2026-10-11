# 396 — Nothing wakes the server while nobody is using it

**Version:** 0.3.436 · Status: **locked**
Follows [395](395-scale-api-to-zero.md). Once the API scales to zero, every request
from nobody starts an instance and keeps it about 15 minutes.

## Why

Request logs, 30 days, `asr-sentence-reading`, 353 hours with any request:

| Who | Hours |
|---|---|
| Phone, speaking takes | 114 |
| Phone, listening or reading | 69 |
| Phone, paper analysis | 5 |
| Phone, nothing on screen but sync, auth and evidence | 45 |
| Phone, only job polls | 17 |
| Agent scripts only (`Python-urllib`, `/api/status`) | 75 |
| Crawlers only (`/`, `robots.txt`, ExaSearchBot) | 28 |

One job (`job_37721dcb69f7`) was polled 7,116 times over about 8 hours of one
night, every 1–3 s. The job poll runs at 500 ms and kept going off screen.

## Locked

1. `AppForeground` (`mobile/lib/services/app_foreground.dart`) follows the app
   lifecycle. `paused`, `hidden` and `detached` are away; `inactive` is not.
   `resting` is away for `kAwayPollFor` (30 min).
2. The ingest job poll waits through `pollPause`. On screen: its own interval.
   Away: once per `kAwayPollEvery` (1 min), which keeps the analyzing instance
   alive. Resting: no request until the app is back. Parked time is added to the
   absolute deadline and the idle timer restarts, so coming back is not a timeout.
   The first park writes `ingest_poll_tick` stage `poll_parked`.
3. The harmonize residual poll (3 s) and the open translate poll (8 s) skip ticks
   while away. Off-screen ticks are not translate attempts.
4. The evidence bus does not flush while resting. Rows wait in the ring. Pausing
   flushes once.
5. `/robots.txt` disallows everything, is open without login, and `/` sends
   `X-Robots-Tag: noindex, nofollow`.
6. `session_freshness_guard.py` reads the live version from the Cloud Run service
   (`ASR_RELEASE_VERSION`, `ASR_DEPLOY_GIT_SHA` on the serving revision) and does
   not call `/api/status`. It falls back to `/api/status` when the service read
   fails or the revision is not fully serving. `ASR_FRESHNESS_LIVE=http` forces
   the old path. Output has `live_source`. Deploy guards still call the app; a
   deploy starts an instance anyway.

## Not changed

Background upload and WorkManager resume (design/75, 76) still run off screen.
A crawler that ignores `robots.txt` still wakes the server.

## Tests

`mobile/test/app_foreground_test.dart`, `tests/test_wake_less_396.py`.
