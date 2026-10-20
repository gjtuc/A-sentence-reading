# 428 — F11 works like the full-screen button

## Problem

Clicking the other window, then pressing the app's full-screen button in this
window, fills both windows (design/427: the earlier click still allows one more
full screen for about 5 s). Pressing F11 instead filled only this window.

Chrome's own F11 is browser full screen: the page never calls
`requestFullscreen`, so the app does not know and never tells the other window.

## Change

`full_screen_web.dart` listens for `keydown` in the capture phase. On F11 (not a
repeat) it calls `preventDefault` + `stopPropagation` and runs
`toggleFullScreen()`, the same path as the button. A key press grants
activation like a click, so the button's rules hold:

- this window enters, then tells the other window;
- the other window enters at once if it was clicked in the last few seconds,
  otherwise it shows the design/427 notice and waits for one click;
- F11 while full screen leaves, and the other window follows.

F11 is not a reserved Chrome key, so the page may take it. The design/427
"next click" listener skips F11 (and Esc) so the key is not used twice.

`onNextGestureSwallowed` now takes a handler that returns whether it entered.
The click is swallowed only then; a stale wait lets the click through.

## Measured (`.cache/fs_probe/probe.py --f11`, Chrome CDP real input)

| Case | This window | Other window |
|---|---|---|
| click the figure window, then F11 in main | full | full |
| click main, then F11 in the figure window | full | full |
| F11 in main with no earlier click | full | not full (waits for its click) |

## Text

Button tooltip `전체 화면 (F11)`; settings subtitle adds F11.
