# 427 - One click fills one window

## Problem

After design/426 the messages arrived, but full screen from the sentence window
still did not reach the figure window, except once right after using the
figure window. Exits followed only when the other window was full screen.

## Measured

`.cache/fs_probe` (two windows in Chrome over DevTools, real mouse input):

| click in | order | clicked window | other window |
|---|---|---|---|
| main | full screen, then delegate | full | delegation throws `NotAllowedError` (no activation left); plain message, enter fails |
| figure | same | full | same |
| main | delegate, then full screen | enter fails | full |
| figure | same | enter fails | full |

`requestFullscreen` and `postMessage(..., {delegate: 'fullscreen'})` each use up
the click's activation. One click fills exactly one window, in either direction.
The "once" came from a click left over within ~5 s: the exit button press does
not use up its activation, so the other window could still enter with it.

## Change

- `enterFullScreen` fills this window, then posts a plain enter. No delegation.
- The other window tries at once (a recent click of its own may still allow
  it). Otherwise `fullScreenAwaitsClick` turns on: a SnackBar in that window
  says one click there will follow, and the next press anywhere enters full
  screen. That press and its release are stopped at `window` capture, so the
  app under it does not also act on it (it could toggle full screen back off).
- Esc is not a click for this (it never carries activation).
- Leaving needs no click and follows at once, as before.

Probe of this flow: main click fills main, a press in the figure window fills
it with 0 app clicks seen, and main's exit takes both out.
