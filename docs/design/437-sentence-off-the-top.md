# 437 — The phone sentence off the top edge, and section names on the phone

## Ask

The phone sentence sits against the top of its pane. Move it down, either to
the middle or somewhat above it, allowing for the figure pane below that may or
may not be shown. And when a tap hides the header, a new section cannot be seen;
show it as the web does.

## Looked up

- The optical centre of a field sits above the geometric one, by about 5–10% of
  its height. Something centred by measurement looks low.
- The first fixations on a screen land near its centre; after 1–2 s of reading
  the eye goes to the first line and the left edge.
- Teleprompters fix the read line a quarter to a third down the screen.

The pane is the frame, not the screen. With the figure pane below, the middle of
the sentence pane is a quarter to a third down the screen, the teleprompter
line. Without it, it is just above the middle of the screen.

## Change

- The phone uses the web's placement (design/414, `kWebSentenceAlign`). The
  sentence block's middle sits at about 40% of the pane's height, left aligned,
  with 12 px above and below. A sentence taller than the pane starts at the top
  and scrolls (design/435).
- The section line (design/430) shows on the phone too. It sits above the first
  sentence of a section and, under a section's last sentence, names the next
  one. Its name is at least 12 px.
- The user chose this over a first line fixed a quarter down. With that
  alternative, the first line would not move between sentences, but short
  sentences would leave the pane empty below.

Files: `screens/reader_screen.dart` (`_readingColumn`, `_sectionBreak`).

## Not covered

- Hiding the header gives the pane its height, so the centred sentence moves
  down by half the header's height.
