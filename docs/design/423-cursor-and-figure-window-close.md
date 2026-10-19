# 423 - The idle cursor really hides; the figure window closes with the main one

## Problem

1. After a click, the buttons faded after 3 s (design/414) but the cursor often
   stayed. The hidden cursor was set on a region around the reader. A cursor is
   taken from the innermost region under the pointer first, so a button or a
   tappable sentence under a resting pointer kept its hand cursor.
2. Closing the sentence window left the figure window open; it had to be
   closed too.

## Change

- `widgets/idle_cursor_layer.dart` puts the hidden cursor on a see-through
  layer above the reader (`MouseRegion(opaque: false)` filling a `Stack`). It is
  hit first, so its cursor wins; clicks and hovers still reach what is below.
  Test: a click-cursor spot under a still pointer turns to none and back.
- The main window already says `bye` on `pagehide` (design/415). The figure
  window now keeps the main windows it hears (`hello`), and when the last live
  one says `bye` it calls `onMainGone`, which closes the window. A script may
  close it because the main window opened it.

## Limits

- Reloading the sentence window (F5) is a `pagehide` too, so the figure window
  closes and opens again by design/420.
- With two main windows (a tab and the app), the figure window stays until both
  are gone.
- A figure window typed into the address bar by hand cannot be closed by script.
