# design/491 - the library stays usable while an analysis runs

## Problem

While a file was being analysed (upload queue or reanalysis), every card was locked: no open, no hold menu, no selection. A queue of several files could lock the library for many minutes, including the new title and kind edits (design/490).

## Rule

- Cards open and the hold menu works during an upload or a reanalysis. Only opening another paper (`opening`) and a delete in progress still lock them.
- `LibraryController.busyCacheIds` is the set an analysis writes into: the card being reanalysed, and a card whose content hash matches the active queue item. Tapping or holding one shows "지금 분석 중인 문서예요. 끝나면 열 수 있어요." and does nothing else; its selection checkbox is off.
- Drag-reorder, "짝과 합치기", figure/harmonize retry and retention stay locked during an analysis, as before. Reorder races the list refresh at the end of an ingest; merge is one heavy job at a time on the server.

## Auto-open

design/221 opens the first finished queue item. That is wrong once the reader may have opened something else:

- A paper the reader opens while the queue runs consumes the one auto-open (`_uploadQueueAutoOpened`) and clears a pending one for another paper.
- The library screen skips a pending auto-open when its ticker is off (the reader surface is up).

## Not changed

The open path, the ingest poll and the hang watchdog were already separate per operation; opening a paper does not touch the ingest's hang track (`_onIngestHangLocal` checks its own op id).
