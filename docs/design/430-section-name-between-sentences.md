# 430 — Section name between sentences

## Ask

When the mouse is still, the title row with "Introduction 17 / 19" fades
(design/414), so a new section starts without any sign. A paper read that way
feels wrong.

## Change (web reader)

- `sectionStartLabel(sentences, i)` (`reader_nav_labels.dart`): the display name
  of sentence `i`'s section when `i` starts a section (first sentence, or the
  one before is in another section), else `''`.
- The current sentence starts a section: its name sits between the faded
  sentence above and the current one.
- The next sentence starts a section: its name sits between the current one and
  the faded sentence below.
- The faded neighbour now shows across a section start too (before 430 it was
  hidden there), so the screen keeps the same shape: neighbour, name, sentence.
- The name is a small line `── Experimental ──`. It is not chrome: it stays
  when the buttons fade, and it shows even with neighbour sentences off.
- Phone: unchanged (the phone header never fades).
