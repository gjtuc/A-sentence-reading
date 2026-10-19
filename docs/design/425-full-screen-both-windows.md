# 425 - Full screen for both windows at once

## Problem

Full screen in the sentence window left the figure window as it was; it needed
its own click on its own button.

## Change

- The pair talk by `postMessage` to each other's window object: the figure
  window the main one opened (`window.open` result), or `window.opener` in the
  figure window (`peerWindow`). BroadcastChannel cannot carry the next part.
- Entering full screen (button, setting, launch click) also posts
  `asr_full_screen_enter` with `delegate: 'fullscreen'` (capability delegation,
  Chrome and Edge). The click's right to go full screen goes with the message,
  so the other window enters inside its message handler.
- Without delegation (other browsers, or the click's right already used) the
  plain message arrives and the other window enters on its own next click.
- Leaving full screen in one (Esc, button) posts `asr_full_screen_exit`; leaving
  needs no click, so the other follows at once. Echoes stop because a window
  that is not full screen ignores an exit and does not answer it.

## Limits

- Whether one click is enough depends on the browser keeping the click's right
  after the first window used it. If not, the other window takes one click
  anywhere, not on its button.
