# 432 — AI in its own window; one click back to full screen

## Ask

Asking AI from the installed PC app opened Google in a tab of whatever Chrome
window was open. Coming back meant finding the app and pressing full screen
again, every time.

## Measured (`.cache/fs_probe/probe.py --open`, Chrome CDP real input)

| Case | Full screen after |
|---|---|
| full-screen page opens a new tab | ends |
| full-screen page opens a popup window | ends |
| the AI page closes | stays ended |
| one click in the page after that | back |

Chrome ends full screen whenever the full-screen page opens another page, on
purpose (a page must not cover what it opened). A new window alone cannot keep
it. In headless Chrome (one virtual screen) the figure window ended too, even
untold; on two real monitors it may stay.

## Change

- Web: `openAiWindow` (`services/ai_window*.dart`) opens the AI page as a popup
  window named `asr_ai`, centred on the app window, 55% x 85% of the screen.
  Asking again reuses and focuses it. Closing it lands back on the app.
  The phone still hands off to the browser app.
- Before opening, `fullScreenStepAway()` marks the time. An exit within 3 s
  of it is not the user leaving: the figure window is not told to leave, and
  the next click here (swallowed, like design/427) enters full screen again
  and tells the figure window. If the figure window ended too, it shows the
  design/427 notice and waits for its own click.
- A later Esc or F11 is the user leaving, and the figure window follows as
  before.
