# 415 - A second window for figures (two monitors)

## Problem

With two monitors the web reader still showed sentence and figure stacked in one
window. The reader asked for sentences on one monitor and figures on the other.

## Shape

The main window's title row has 「그림 창 따로 열기」 (web, window at least 720 px). It
opens the same app at `?pane=figure` in a named popup (`asr_figure`), so pressing it
again focuses the open one. The user moves that window to the other monitor.

- The figure window shows only the figure panel. With nothing open it says so instead
  of showing the library, and it does not open the last paper read.
- While a figure window is open, the main window shows only sentences. When it closes
  (or is not heard from for 5 s) the main window goes back to its own layout.
- Both windows are the same browser and the same login, so they read the same papers
  from browser storage.

## Link (`services/pane_link.dart`)

A `BroadcastChannel('asr_pane_v1')` between the windows, JSON text messages:

- `hello` every 2 s with the role. A figure window with nothing open adds `need`; the
  main window answers with its spot. That also covers a figure window that was still
  logging in when the first spot came.
- `spot` (`cache`, `si`, `fi`) after every saved move (`LibraryController.onSpotSaved`,
  from `persistOpenedProgress`) and when the main window opens a paper.
- `bye` on `pagehide`.

The receiver uses `LibraryController.followPane`: same paper only, the indices must
fit the paper, nothing while paint mode holds the reader. Only the figure window
follows to another paper (`openByCacheId`). A followed spot is saved with
`toPane: false`, so it is not sent back; an echo landing after the next key press
would pull the sender back a sentence.

Keys work in both: ←/→ in the figure window move the figure, and the main window
follows; Shift+←/→ in the main window move the figure window.

Spots from other devices (design/411) still arrive through the server; a followed
device spot is saved with `toPane: true`, so the figure window follows the phone too.

## Not done

- One window split left and right. Two windows cover two monitors better (each can be
  full screen), so this was not built.

## Tests

- `mobile/test/pane_link_test.dart`
