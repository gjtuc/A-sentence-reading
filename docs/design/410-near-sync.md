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
  networks may not reach each other; the dialog then says to use the same Wi-Fi.

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

## Known limits

- Without TURN a cross-network pair can fail (`open_timeout` / `ice_failed`).
- The whole pack of one paper is held in memory while it moves.
- Practice records, recordings, notes and bookmarks are not synced yet (step 2b).

## Tests

- `tests/test_design_410_near_links.py`: host/join round trip, other accounts cannot
  take a link, newest first and taken once, answer only after claim and once, expiry,
  bad input, login.
- `mobile/test/near_sync_test.dart`: both directions byte for byte, a 5 MB paper through
  the 2 MB window, reading spots both ways, nothing to move, a cut pipe fails, an
  escaping path is refused, `mergeProgressRows`, and two browser-stored libraries
  syncing through the real `PaperDiskStore`.
