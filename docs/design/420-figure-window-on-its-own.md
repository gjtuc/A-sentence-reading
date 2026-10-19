# 420 - The figure window opens on its own, and one colour setting on the web

## Figure window

design/415 opened the figure window from a button. 「그림 창 자동으로 열기」 (web
settings, off by default) opens it when a paper opens in the main window.

- The main window waits a little past one hello (`kPaneBeat`) after the paper
  opens, so a figure window already open is not reloaded by a second `open`.
- Once per main window (`paneAutoOpenDue`): a figure window the reader closed is
  not reopened until the main window is reloaded.
- A window opened without a click is a blocked popup unless the site is allowed
  popups. When `open` is refused, the next pointer press or key anywhere opens it
  (`openFigurePaneOnNextGesture`), and a snackbar says so once.
- Placement: with the browser's 「window management」 permission (Chrome, Edge),
  `getScreenDetails` lists the screens and the figure window fills one other than
  this window's (`paneWindowFeatures`). The question is asked when the setting is
  turned on, inside that click; afterwards an already given answer is read at
  start. Without it the window opens over this one, as before. The button uses the
  same placement.

## One colour setting

The web had 「테마」 (system, light, dark: the whole app) and 「배경」 (app, dim
grey, paper, white: the reader only). On the web they are one setting, 「화면
색」: 시스템 follows the system's light or dark with the app colours; the others
paint every screen, the library, settings and the figure window included
(`webThemeMode`, `webAppTheme` in `MaterialApp`). The reader no longer repaints
itself (`WebPageTheme` is gone). The phone keeps 「테마」 and has no 「화면 색」.
