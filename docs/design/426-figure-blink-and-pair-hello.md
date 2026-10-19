# 426 - Figures stop blinking; full screen follows from the main window too

## Problem

1. Phone and web: the figure blinked whenever something loaded. Any
   `notifyListeners` rebuilt `_FigureImage`, which ran `decodeRasterDataUrl` again.
   New bytes make a new `MemoryImage` (it compares by bytes identity), so Flutter
   decoded the image again and drew nothing until it was done.
2. design/425 worked from the figure window only. Full screen and Esc in the
   main window did not reach the figure window, and exits need no click, so the
   message never arrived: the main window's `window.open` result was not a
   usable target. The figure window posts to `window.opener`, which works.

## Change

- `decodeRasterDataUrlCached`: the last `kFigureBytesCacheSize` (8) figures keep
  their decoded bytes, keyed by the data URL (equal strings match). The reader
  uses it; the disk stores keep the plain decoder.
- `gaplessPlayback: true` on the reader figure images keeps the old picture on
  screen while a new one decodes.
- `startPair`: the figure window posts `asr_pair_hello` to its opener at start;
  the main window keeps `MessageEvent.source` as the figure window
  (`peerWindow` prefers it, then the `window.open` result, then the opener).

## Check

- Test: an equal data URL read again gives identical bytes; the ninth newer
  figure pushes one out.
- On the two monitors: full screen and Esc in the sentence window should now
  move the figure window as well.
