# 422 - Full screen on the web

## Problem

The installed web app runs in a window with a title bar, and the taskbar stays
on screen. The user wants only the app on screen while reading, on both
monitors.

## Change

- `services/full_screen.dart` wraps the browser Fullscreen API
  (`full_screen_web.dart`; the phone stub does nothing). `fullScreenOn` follows
  `fullscreenchange`, so an exit by Esc shows on the button.
- Setting 「전체 화면으로 보기」 (`WebReadingPrefs.fullScreen`, off by default).
  Turning it on enters full screen in that click. With it on, each window
  (main and figure) enters full screen on its first click or key after launch.
- A full screen button sits right of the title in the reader (web).
- Opening a window can end full screen, so the main window holds full screen
  while the figure window is still to open on its own (`fullScreenWaitsForPane`:
  not tried yet, or waiting for its click). The click after takes full screen.
  A refused try waits for the next click.
- Esc leaves full screen (the browser owns that key). The reader's Esc-to-library
  (design/421) is skipped while full screen is on and for 400 ms after it ends.

## Limits

- No full screen without a click: the browser refuses it at launch.
- With 「그림 창 자동으로 열기」 on and the library shown at launch, full screen
  starts only once a paper opens and the figure window is out.
- F11 is the browser's own full screen; it is not seen by `fullScreenOn`.
