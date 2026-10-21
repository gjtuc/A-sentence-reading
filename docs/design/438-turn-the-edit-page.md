# 438 — Turning pages in the figure layout editor

## Ask

The figure layout editor's bar has "< p.1 >". Drop it, and turn the page with a
left or right swipe as the figure pane does. On the web, the keyboard turns it
too.

## Change

- The arrows and "p.N" are gone. Under the title, the bar shows "3 / 12쪽".
- A swipe turns the page in Pan and in Select, the mode the editor opens in.
  Before, the edge swipe (`panEdgePageTurn`) ran in Pan only, so most readers
  never met it. Zoomed in, the page pans first and turns when pulled past the
  edge, as before.
- Crop keeps its drag for the crop frame and has no swipe.
- ←/→ turn the page, on the web and on any keyboard. The handler acts only while
  the editor is the top route, so a dialog over it keeps its keys. It also stops
  the key before the reader underneath sees it.
- The first and last pages stop the turn. The old next arrow had no upper
  bound.

Files: `screens/figure_edit_screen.dart`, `test/figure_edit_page_turn_test.dart`.
