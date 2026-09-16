# 297 — Session title from Info.Title or the SI head paragraph

Version: **0.3.290** · Status: **locked**

## Why

Ingest set `session.title` to the filename stem, then to the first `section=title` card. Elsevier stems are codes. PDF `Info.Title` and the 13.4pt lines are the paper title. SI `dc:title` is `Supporting Information`; the next paragraph is the paper title, but SI cards are forced to `section=supplementary` so that line never became the title. A bad Gemini title card (authors / ABSTRACT) could overwrite a good title. `title_guess` was stored and never applied.

## Rules

1. Prefer a usable `Info.Title`, then the first-page largest font run, then the paragraph after an SI banner, then a usable `title_guess`, then a usable `section=title` card.
2. Reject SI banners, Elsevier `1-s2.0-S…` stems, author dumps, and ABSTRACT / Keywords mashes.
3. A code-like stem is only a last resort (`stem_fallback`).
4. `title_pick_done` records `title_source`, `title_class`, `char_n` — not the title text.

## Non-goals

- Changing pairing rules beyond sharing this title  
- Version is this ship; extract behavior stays [295](295-docx-vml-caption-split.md)  

## Early measure

Do not delete `_ELSEVIER_STEM` when adding another regex in `title_replay.py`. The replay call must keep `sentences=sentences`. Both are source locks in `tests/test_title_replay_console.py`, not only a runtime call.

## Acceptance

`tests/test_session_title_pick.py`
