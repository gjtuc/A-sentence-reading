# 409 - The web keeps papers in browser storage (sync plan, step 1)

## Problem

design/408 made the web keep nothing, so the library error went away. But the server
does not keep papers either. design/185 wipes a paper from the server once the phone
pulls it and ACKs, and design/185 J19 wipes an unpulled one 72 hours after the last
manifest. The web library therefore showed only papers the phone had not pulled yet,
and only while the server still had them.

The user chose to keep papers on each device and to sync phone and web directly,
without the server holding them:

1. Browser storage (this document).
2. Direct sync by a one-time QR code, with files going device to device. The pattern
   comes from the 던지고 받기 project (`near_sync.dart`, WebRTC). Only short connection
   messages go through our server.
3. USB sync (WebUSB, Android accessory mode). Windows needs WinUSB on the accessory
   device once. This PC already has it (`libwdi`, `USB\VID_18D1&PID_2D01`), installed
   for 던지고 받기. A PC without it gets a notice and a setup file.

## What changed

- **`services/disk_fs.dart`.** The few file operations the paper store uses (exists,
  read, write, rename, delete, list). `IoDiskFs` uses dart:io on a phone. On the web,
  `browser_disk_web.dart` uses IndexedDB (database `asr_disk`, store `files`, key = path,
  value = bytes), behind a conditional import. Folders exist only through the files
  under them. `MemoryDiskFs` follows the same rule for VM tests (`debugBrowserDisk`).
- **Kept papers survive low disk.** The web store asks the browser for persistent
  storage (`navigator.storage.persist()`). Otherwise the browser may clear it.
- **`PaperDiskStore`** reads and writes through `_root()` / `_dirOf()`. These point at the
  app folder on a phone and at `/asr_paper_disk/u/<uid>` in browser storage on the web.
  `uidRoot()`, `paperDir()` and `localSourcePath()` stay app-folder only (null on the web).
  The Android mirror, the residue sweep and the native PDF renderer need real paths.
- **The web takes a copy and never ACKs.** `_runPaperHandoff` pulls and checks the
  files as on the phone. When `localDiskAvailable` is false, it does not POST
  `handoff-ack`, and it reports `paper_handoff_done stage=copied ackOk=false`. The phone
  still pulls the paper and ACKs, and the wipe happens then. The web copy stays in the
  library through `mergeRemoteWithLocal`, and it opens from browser storage
  (`reader_open stage=local_paper_disk`).

## Known limits

- The web only gets a paper the server still has. Moving papers the phone already owns
  is step 2.
- A web handoff rebuilds the manifest, which restarts the 72-hour abandon clock. That
  only delays the wipe.
- Figure cache, shadowing, notes archive and edit stash still keep nothing on the web
  (design/408).

## Tests

- `mobile/test/web_no_local_disk_test.dart`, group `design/409 browser storage`. The
  store keeps a session and index in browser storage, separately for each account, and
  leaves no `.part` file. A bound library pulls a paper with zero ACKs. After the server
  list empties, the paper is still listed and opens with no `/open` call.
- `tests/test_design_409_browser_paper_store.py`
