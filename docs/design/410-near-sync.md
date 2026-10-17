# 410 - Phone and web sync papers directly (sync plan, step 2a)

## Problem

design/409 lets the web keep papers, but it only gets papers the server still has. A
paper the phone already pulled and ACKed is gone from the server (design/185), so the
web never sees it. The reading spot also stayed on each device.

The user wants phone and web to sync like the 던지고 받기 app, without the server
holding papers. Step 2a moves papers and reading spots. Practice records, recordings,
notes and bookmarks are step 2b.

## How it connects

- The web is the host. 「폰과 동기화」 builds a WebRTC offer with one ordered data
  channel, waits until ICE gathering completes (at most 4 s), and posts the whole
  description to `POST /api/near/links`. No candidate trickle, so the server only
  carries two messages.
- The phone joins. 「웹과 동기화」 calls `POST /api/near/links/claim`, which hands it the
  newest open link **of the same account**. A QR code is not needed for that, since both
  devices are signed in to one account, so there is no camera or scanner package. The
  phone answers with `POST /api/near/links/{id}/answer`; the web polls
  `GET /api/near/links/{id}` every 1.5 s and deletes the link once it has the answer.
- A link lives 3 minutes and is taken once. It is stored under the account
  (`users/{uid}/near_links/{id}.json` in GCS; in memory without GCS). An SDP is capped at
  64 KB. The routes need login and pass the paid-access gate.
- ICE uses `stun:stun.l.google.com:19302` only. Without TURN, two devices on different
  networks often cannot reach each other. The user's office has no Wi-Fi: the phone is
  on mobile data and the PC behind a company firewall.

## Relay when the devices cannot reach each other (`services/near_relay.dart`)

If the data channel is not open 10 s after the description exchange
(`kNearDirectLimit`), both sides close the peer connection and run the same frames
through the server. It uses the same HTTPS the web app already uses, so a firewall
that lets the web app in lets the relay in.

- Frames are bundled as `[u32 length][frame]...`, at most 1 MB, flushed after 150 ms.
  Each side posts numbered bundles: `POST /api/near/relay/{link}/{h|j}/{seq}` (4 MB cap).
- The other side polls `GET .../{other side}/{seq}` every 0.7 s when idle and at once
  after a hit. Asking for `seq` deletes `seq - 1`, so a bundle stays only until it is read.
- Bundles live under the account (`users/{uid}/near_relay/...`). A failed or cancelled
  run deletes its bundles (`DELETE /api/near/relay/{link}`), and a new link wipes
  anything an earlier run left.
- A put is retried 4 times (0.5, 1, 2, 4 s); 5 failed polls in a row end the run.
- `near_sync_done` records `relay=1` for a relayed run.

## What moves (`services/near_sync.dart`)

Both sides run the same steps over a `NearPipe`:

1. `inv`: papers held (`id`, `title`, `hash`) and every reading-spot row.
2. `want`: ids the other side has and this side lacks. Nothing is replaced or deleted.
3. For each wanted id: a `paper` header with the file list, then 16 KB byte frames. The
   sender keeps at most 2 MB unacknowledged; the receiver acks every 256 KB and at the
   end of each paper. Then `sent`.
4. After storing everything, `fin`. Done when both `fin` are exchanged.

Every frame is binary with a one-byte kind (1 = JSON, 2 = bytes). The 던지고 받기 app
found that a browser data channel can deliver text frames out of order against binary
ones.

- Papers come from `collectTransferPackFiles` and land through `replaceFromTransferPack`
  (`services/near_library_local.dart`). A file path must stay inside the paper folder
  (`nearSafeRel`).
- Reading spots merge through `mergeProgressRows`: the row with the newer `at` wins the
  spot (sentence, figure, layout, section), and `last_read_left_at` keeps the later time.
- 45 s with no frame, a closed channel or a failed ICE ends the run with a code. The
  dialog shows it in plain Korean, and `near_sync_done` records the side, codes, counts,
  bytes and time.

## Practice files (step 2b, 0.3.447)

Bookmarks, annotations, notes and the practice calendar and skill stores already
sync per account through the server (`/api/bookmarks/sync`, `/api/annotations/sync`,
`/api/notes/sync`, `/api/practice/*/sync`). Only shadowing lives on the device alone:
`chunks.json`, `takes.json` and `voice/*.bin` per paper (design/187).

- `ShadowingDiskStore` now reads and writes through `disk_fs` like the paper store:
  the app folder on a phone, `/asr_shadowing/u/<uid>` in browser storage on the web.
- `inv` carries `extras`: per paper, the voice file names held. After the papers, each
  side sends an `extra` item for every paper both will hold, with the chunk plan, the
  takes and only the voice files the other side lacks.
- `mergePackFiles` never replaces: a voice file is written only when missing, the chunk
  plan only when there is none, and a take slot only when it is empty here
  (`mergeShadowingTakes`).

## Speed evidence

The first live run moved 58 MB directly in about 7 minutes. `near_sync_done` now also
records `open_ms`, the selected candidate pair (`local_kind`, `remote_kind`, `proto`,
`rtt_ms`) and where the time went: `pack_ms` (reading files), `send_ms` (awaiting the
channel), `room_ms` (waiting for acks), `store_ms` and `sync_ms`. A large `room_ms`
points at the ack window, a large `send_ms` at the channel or the network.

0.3.447 run (phone on mobile data, PC on the office network, `srflx`/`srflx` over UDP,
RTT 31-64 ms): no papers moved, but the first practice-file pass sent 368 files.
`room_ms` was 495 s of a 527 s run, `send_ms` 2 s, web `store_ms` 35 s. The web acks
every 256 KB as bytes arrive, so `room_ms` here is the time the bytes spend in the
channel, not a late ack: native `send` only fills the channel buffer. A 2 MB window at
64 ms RTT allows far more than the ~130 KB/s seen in both runs, so the path itself is
the limit, not the window. Voices the other side holds are skipped, so later runs move
only new voices and the two small JSON files per paper.

The dialog used to show only paper counts, so a practice-file pass looked frozen at
"0/0 (0.0MB)". `NearSyncProgress.extraBytesIn/Out` now count user-file bytes (reported
at most every 250 ms), the dialog shows them on their own line, and `near_sync_done`
records `extra_bytes_in` / `extra_bytes_out`.

## Known limits

- A relayed paper passes through the server for a few seconds (HTTPS, deleted once read).
- If a channel opens right at the 10 s boundary, one side may go direct and the other
  relay; that run fails and a retry works.
- The whole pack of one paper is held in memory while it moves.
- Two different takes in the same slot: the one already held stays.
- The web holds shadowing files but its shadowing screen is web step 6.

## Tests

- `tests/test_design_410_near_links.py`: host/join round trip, other accounts cannot
  take a link, newest first and taken once, answer only after claim and once, expiry,
  bad input, login.
- `mobile/test/near_sync_test.dart`: both directions byte for byte, a 5 MB paper through
  the 2 MB window, reading spots both ways, nothing to move, a cut pipe fails, an
  escaping path is refused, `mergeProgressRows`, and two browser-stored libraries
  syncing through the real `PaperDiskStore`. Group `design/410 relay`: bundle round
  trip, a 3 MB paper and reading spots through a fake relay with one failed put and
  nothing read left behind, and a relay that keeps failing ends the run.
- `tests/test_design_410_near_links.py` also covers relay bundles passing once and
  being deleted, bad relay input, and a new link wiping leftovers.
