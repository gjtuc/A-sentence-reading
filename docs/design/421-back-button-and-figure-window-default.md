# 421 — Back button on the web, figure window on by default

## Problem

1. The site installed as an app (`display: standalone`) has no browser back
   button or address bar. The reader had no way back to the library, so a
   paper once open could not be left.
2. The figure window did not open on launch: design/420 shipped
   「그림 창 자동으로 열기」 off, so it waited for a switch nobody had touched.

## Change

- `ReaderScreen.onBack` — HomeShell passes `_goLibrary` (the main window only;
  the figure window has no library). On the web an `arrow_back` button sits left
  of the title, and Esc does the same under the same guards as the arrow keys
  (reader on screen, no annotation editor open). The phone keeps its own back.
- `WebReadingPrefs.autoFigurePane` defaults to `true`. A saved `false` stays off.
- The click that opens a blocked figure window (and the reader's open button)
  also asks for the browser's 「window management」 permission, so the next
  window goes to the other monitor. Before, only the settings switch asked.
- Popup notices point to the blocked-popup mark at the top right of the window,
  not the address bar, which the installed app does not have.

## Limits

- Without popup permission the first window opens on the first click or key,
  not by itself. After 「팝업 허용」 it opens at launch.
- The window that opens on that first click is placed before the screen answer
  arrives; the other monitor is used from the next open.
