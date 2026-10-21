# 435 — A bigger sentence on the phone

## Ask

Reading on the phone tires quickly because the sentence is small. Let the
sentence window's text size be set, much larger than now. Bigger text needs more
room, so:

- the bar between the sentence and figure panes keeps where the reader left it;
- a long sentence scrolls up and down inside its pane;
- the tap that hides the sentence buttons also hides the title row (title and
  "연습") and the references row when it is folded, as the web fades them.

## Change

- Settings, off the web: "문장 글자 크기", a slider from 16 (the old size) to 40 in
  steps of 2, with a sample line. The Korean line under the sentence keeps the old
  14 : 16 ratio. The web reader keeps its own sizes (design/411).
- The split bar: when a drag ends in the middle, that fraction is saved and every
  later split (a new paper, back from a full pane, the automatic split at the
  first figure mention, a figure chip) opens there. Releasing near the default
  (the magnet and its guide line, design/98) saves the default again. Snapping to
  an edge keeps the saved value. A saved value outside 0.15–0.85 is ignored.
- A tap on the sentence or figure (`_chromeVisible`) now also removes the title
  row and, only while folded, the references row. An open reference list stays.
  The rows collapse, so the sentence gets their height.
- The sentence pane already scrolled when the text ran past it. It now starts at
  the top for each sentence; before, the next sentence opened at the old scroll
  offset.

Files: `state/reader_prefs.dart` (new), `screens/reader_screen.dart`,
`screens/settings_screen.dart`.

## Not covered

- While a highlight is being painted the pane does not scroll (design/182: the
  drag paints).
- In sentence-only view a swipe up opens the figure (design/156). When the
  sentence overflows, the same swipe may scroll it instead; not checked on a
  device yet.
