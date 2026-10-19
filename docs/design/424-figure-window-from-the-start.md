# 424 - Sentences only from the start; the figure window fills its screen

## Problem

1. With 「그림 창 자동으로 열기」 on, the main window opened with sentences on top
   and figures below, and the figures moved out only when the figure window came
   up (design/420 waits a hello, then the window loads). The jump is pointless
   when the setting already says where figures go.
2. The figure window came up smaller than its screen. `window.open` width and
   height are the inner size, and without the 「창 관리」 permission it is a plain
   1100x850 window. The web has no maximize call.

## Change

- `PaneLink.figureExpected` (main window): set at start when the setting is on.
  `figureShown = figureOpen || figureExpected` decides the sentences-only layout.
  It ends at the figure window's first hello, when the setting is off, or 20 s
  after an open with no hello (the figures come back).
- New message `place` (main to figure): a screen rectangle. The figure window
  `moveTo` + `resizeTo` (outer size) it, which covers the same area as
  maximized. Skipped while that window is full screen.
- The main window sends `place` with the screen other than its own
  (`paneTargetScreen`) on the figure window's first hello, and again once the
  permission is given.
- When the permission is not given yet and the setting is on, the first click in
  the main window asks for it, after that click's own work (a figure window it
  opens comes first).

## Limits

- Without the permission the figure window cannot be moved to the other screen;
  it opens over the main window until the first click allows it.
- With popups blocked, the figures are nowhere until that first click opens the
  figure window.
