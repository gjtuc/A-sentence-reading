# 441 — The references fold stays, and a still mouse leaves no gap

## Ask

1. The 참고문헌 row folds and opens. Keep what the reader chose, as the split bar
   keeps its place (design/435). Web and phone.
2. On the web, a still mouse fades the title row and the button rows after 3 s
   (design/414), but their space stays, so an empty band floats where the header
   was. A tap that hides them folds the space; the still mouse should too.

## Change

**Fold.** `ReaderPrefs.citeCollapsed` (`reader_cite_collapsed_v1`) replaces the
reader's own flag. It is one value for every paper, saved on change and loaded with
the other reader prefs, so it holds across papers and restarts. Before, it lived in
the reader state and opened again for each paper (design/183).

**Still mouse.** `_FadeChrome` now folds its height with the fade, in the same 600 ms
(`AnimatedAlign` `heightFactor` under a `ClipRect`). Any mouse move brings it back in
150 ms. One widget carries the title row, the sentence and figure button rows and a
folded references row, so all four fold. The sentence moves a little when they go
and come back; the reader chose that over an empty band. design/414's "they keep
their space" no longer holds.

The phone never fades on a still mouse, so it is unchanged.

Files: `mobile/lib/state/reader_prefs.dart`, `mobile/lib/screens/reader_screen.dart`,
`mobile/test/reader_screen_widget_test.dart`.
