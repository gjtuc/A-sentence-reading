# 434 — Ask AI about the figure in the figure window

## Ask

In the sentence window a key opens "이 문장을 AI에게 묻기" and the question is
asked about the sentence shown. Do the same in the figure window, about the figure
shown, on the PC app first.

## Measured (`.cache/clip_probe/clip_test.html`, Chrome, google.com/ai)

| Clipboard | Ctrl+V on the AI page |
|---|---|
| picture and question in one clipboard item | the picture only |
| picture alone | the picture |
| question alone | the question |
| picture with the question drawn under it, sent with no text | answered about the picture and ignored the drawn question; it followed it only when asked again |
| question, then 800 ms later the picture | Ctrl+V the picture, Win+V lists the question; the answer followed the question exactly |

A picture cannot travel in the address the way a sentence does (design/419), and
writing the question into the picture is read as part of the picture. So the
question goes in as text, from Windows' clipboard history.

## Change

- A typed key in the figure window (`figureOnly` layout) opens "이 그림을 AI에게
  묻기": the figure, three steps (question typed or chosen → Ctrl+V for the
  picture → Win+V for the question), the question box and the saved prompts.
- Sending copies the question, waits 800 ms so Win+V keeps both entries, copies
  the figure as PNG (a JPEG is redrawn, since the browser's clipboard takes PNG
  only), and opens google.com/ai in the AI window (design/432).
- "그림만 복사하고 AI 열기" copies the figure alone; the question is typed on the
  AI page.
- The phone is unchanged: Flutter's clipboard there holds text only. Sharing the
  figure and question to the Gemini app is the planned phone path.

Files: `services/figure_clipboard*.dart`, `api/ai_ask.dart` (`runFigureAiAsk`),
`widgets/annotation_toolbar_sheet.dart` (`showFigureAiAskDialog`),
`screens/reader_screen.dart`.

## Not covered

- Figures whose source is an http address rather than bytes in the app do not
  open the dialog.
- Win+V needs Windows clipboard history on; the first Win+V offers to turn it on.
