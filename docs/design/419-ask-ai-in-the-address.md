# 419 - Ask AI without pasting

## Problem

「AI로 묻기」 (design/182) copied the sentence and a saved prompt, then opened
google.com/ai: the reader still had to paste and press Enter there. A question of
one's own had to be saved as a prompt first. The answer cannot be brought back: a
page cannot read another site's page.

## Shape

- Google AI Mode answers a question carried in the address:
  `https://www.google.com/search?udm=50&q=<question>`. `runAiAsk` opens that first;
  the copy-and-open path stays for a question longer than `kAiAskModeMaxUrl` or a
  failed launch. `udm=50` is not documented by Google; if it stops working the old
  path is one fallback away.
- The question is one line, `"<sentence>" <prompt>`: AI Mode drops line breaks,
  which would join the sentence's last word to the prompt's first.
- The long-press sheet has a question field: type, Enter, and it goes with the
  sentence. The saved prompts stay below it.
- On the web reader, a typed letter or Enter (no Ctrl, Alt or Cmd; not the arrows or
  Space, which move or scroll) opens a question box over the current sentence, with
  the saved prompts as chips. The key that opened it is dropped: with no text field
  focused the browser types Latin letters even in Korean mode, so keeping it would
  start a Korean question with a stray letter.
- No snackbar when the question went in the address; the answer is already on the
  screen.
