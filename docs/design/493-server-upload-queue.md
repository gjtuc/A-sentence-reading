# design/493 — Server-held upload queue

Version: 0.3.506

## Problem

The upload queue (design/221) lived only in the app. The app uploaded one PDF, waited
for its analysis, then uploaded the next. Closing the app or losing the phone's
background time stopped the line: nothing after the current file reached the server.

## What changes

The server keeps the line. The app sends every queued file ahead, and the server starts
them one at a time in the order they arrived, with or without the app.

### Server

- `users/{uid}/ingest_queue/queue.json` lists job ids in upload order
  (`src/sentence_reading/llm/ingest_queue.py`). Writes use a generation check, so two
  instances cannot lose each other's additions.
- `POST /api/ingest/uploads/{id}/complete?queue=1` (and `/api/ingest?queue=1`) saves the
  job and its blob as before, but marks the job `queue_waiting` with stage `waiting`
  and does not start a worker. It returns `queued: true` and `queue_position`.
- `_advance_ingest_queue(uid)` walks the line. It drops finished, failed, cancelled or
  missing jobs. The first live job decides:
  - waiting: flip it (`queue_waiting=false`, `queue_started_at`) and start it through
    `_reclaim_ingest_job_from_gcs` (wakes the worker, or runs inline);
  - running with a live lease, or flipped less than 120 s ago: wait;
  - started but its lease ran out: reclaim it.
- Advance runs after an enqueue, when a queue job ends (`_run_ingest_job` finally, on the
  worker), after a waiting job is cancelled, when the owner polls a waiting job (at most
  every 15 s), and from the API sweeper for owners seen on that instance.
- A waiting job is never started by the other paths. `try_claim_lease_with_reason`,
  the worker-wake reclaim, the poll reclaim and `sweep_candidate` all skip
  `queue_waiting`.
- The poll view of a waiting job has `queue_waiting: true`, `queue_ahead` and
  `worker_alive: true`, and the message says how many jobs are ahead.
- When the queue file cannot be written, or GCS or the owner is missing, the job starts
  at once, as before.
- `ASR_INGEST_SERVER_QUEUE=0` turns the queue off.

### App

- `UploadReserveItem.jobId` remembers a file that the server already holds.
- After the head file gets its job, the app uploads the rest of the line with `queue=1`
  (`_sendAheadQueue`), one by one, and stores each job id. It stops at the first error
  (rate limit 429 included) and tries again later; an unsent file is uploaded when its
  turn comes, as before. If a response lacks `queued`, the server has no queue and the
  app stops sending ahead.
- The pump reattaches a sent file by its job id (draft `processing` → `_finishWithPoll`),
  so a file that finished while the app was closed is handed to the device at once.
- Removing a sent file from the queue sheet cancels its server job.
- Polling a waiting job counts as alive: the poll idle timeout, the stall watch and the
  hang watchdog are all reset by `queue_waiting`.

### Evidence

- Server: `ingest_queue_enqueue`, `ingest_queue_advance`.
- App: `upload_queue_send_ahead`.

## Not changed

- Reanalyze and uploads without `queue=1` start at once.
- Files picked on another device are not shown in this device's queue sheet; they appear
  in the library when they finish.
