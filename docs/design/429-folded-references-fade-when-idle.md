# 429 — Folded references fade when the mouse is still

## Ask

The web reader fades the title row and buttons after the mouse is still for
3 s (design/414). The "참고문헌" row stayed. Folding it already says "not while
I read", so it should fade with the rest.

## Change

In the sentence pane, the references header is wrapped in `_FadeChrome` with
`faded: fadeChrome && citeCollapsed`.

- Folded: fades with the title row; its space stays, so the sentence does not
  move. Moving the mouse brings it back, like the other buttons.
- Open: stays, since the list is being read.
- Phone: `fadeChrome` is web-only, so nothing changes there.
