# 401 — a rescan keeps the titles this run already read

## What was wrong

On the PDF import screen, tapping SI 찾아보기 arms the find watch
(`armFindWatch`, 120 s). While it is armed, `pdf_import_screen` rescans the folder
every 4 s through `rescanPdfFolderDebounced(trigger: 'find_watch')`.

Each `_scanPdfFolder` did two things:

1. It rebuilt every `ScannedPdfEntry` with `advisoryState: unknown`, so titles
   already found went back to 제목 확인 중 and were read again.
2. It bumped `_pdfAdvisoryPumpEpoch`, which cancels the title read in flight.

A read of 40 entries in batches of 2 takes longer than 4 s on a large folder, so
the pump was cancelled and restarted on every rescan and never finished. The
rows kept loading for the whole two minutes, including rows whose title was
already on screen.

## Rules

- `keptScanEntry` returns the previous entry object when the file is unchanged
  (same `docUri`, `displayName`, `sizeBytes`, `lastModifiedMs`) and its advisory
  state is not `unknown`. A read in progress is kept too, so its result lands
  in the visible list.
- `_scanPdfFolder` bumps the advisory epoch only when the scanned folder differs
  from the last scan of that browse target. `cancelPdfAdvisoryPump` (screen
  dispose) and sign-out still cancel.
- When a pump ends cancelled, `releaseAbandonedReads` turns its `computing`
  entries back to `unknown`. Otherwise a kept entry would show 제목 확인 중
  forever.
- design/309 is unchanged: no title is written to disk. A fresh app start reads
  every file again.

## Evidence

`pdf_folder_scan_done` adds `n_adv_kept`, the number of entries carried over
from the previous scan.

## Tests

`mobile/test/scan_keeps_read_titles_test.dart`.
