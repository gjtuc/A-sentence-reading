# 414 - Web reading look: centred sentence, page colour, quiet buttons

## Problem

After design/411 the web sentence was large and kept in a column, but it sat at the top
of a tall card with the rest of the screen empty. The page was the app's near-black,
the buttons stayed on screen all the time, and there was no spacing or font choice like
Word's Immersive Reader has.

## What changes (`state/web_reading_prefs.dart`, `screens/reader_screen.dart`)

All of it applies only on the web in a window at least 720 px wide
(`webReadingActive`). The phone look does not change.

- **Centred sentence.** `webReadingColumn` takes the frame height (`viewHeight`) and
  places the column a little above the middle (`kWebSentenceAlign`, y = -0.2). Dead
  centre reads as low. A sentence taller than the frame still scrolls.
- **Page colour.** 앱 그대로 / 어두운 회색 (default) / 종이색 / 흰색. `WebPageTheme` wraps
  the reader in a `Theme` built from the palette plus a `Material`, so text that uses
  `DefaultTextStyle` follows too. 앱 그대로 leaves the app theme alone.
- **Spacing.** 넓게 sets letter spacing 0.05 em, word spacing 0.2 em and line height
  1.9. 보통 keeps design/411 (0.2 px, 0, 1.6).
- **Book font.** 책 글꼴 uses Source Serif 4 (Regular, Italic, Semibold; SIL Open Font
  License) bundled in `mobile/assets/fonts`. It applies to the English sentence only;
  Korean keeps the default font.
- **Quiet buttons.** With the mouse still for 3 s (`kWebChromeIdle`) the title row and
  the sentence and figure button rows fade out and the pointer hides. They keep their
  space, so the sentence does not jump. Any mouse move or click brings them back.
  Arrow keys do not. Paint mode never hides them.
- **Neighbour sentences.** The sentence before and after are shown above and below at
  opacity 0.32, 0.78 of the size, three lines at most. Only inside the same section.
  They ignore taps, so paint and swipe are unchanged.

Settings, 「웹 읽기 화면」, has all five plus the design/411 size and width. They are kept
in shared preferences (`web_reading_page_v1`, `web_reading_spacing_v1`,
`web_reading_font_v1`, `web_reading_autohide_v1`, `web_reading_context_v1`).

## Browser back

Checked while doing this: the root navigator reports to the engine
(`reportsRouteUpdateToEngine`), so the web build runs single-entry history. Browser back
(and the mouse back button) reaches the home shell's `PopScope`, which leaves the reader
for the library exactly as the phone back does: it records the read, reloads the resume
labels and flushes the cursors. Nothing to change.

## Tests

- `mobile/test/web_reading_prefs_test.dart`
