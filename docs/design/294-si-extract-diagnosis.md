# 294 — SI extract diagnosis (counts, not a product fix)

Version: **0.3.289** · Status: **locked**  
Amends [288](288-main-si-index-pairing-evidence.md)  
Context: SI docx with VML `v:imagedata` (no `a:blip`) extracted 0 figures, and heuristic split cut `Fig. S4.` into its own card. Finding that required opening docx XML by hand.

## Why

`figure_extract_done` only said empty=1. That does not distinguish “file has no images” from “images are VML and the walker only sees blips”. Sentence cards had no splitter name and no stub-caption count, so a short caption fragment looked like a real sentence.

## Rules

### D1 — figure census (observability)

`figure_source_census` counts `blip_n`, `imagedata_n`, `caption_n`. `vml_unseen_n` equals `imagedata_n` (walker never reads VML). Emit those fields on existing `figure_extract_done`. **Do not** start extracting VML in this chip.

### D2 — sentence split sensor

New kind `sentence_split_done` (add-only on the floor) when the fallback splitter runs: `splitter` (`pysbd` or `heuristic`), `sentence_n`, `stub_caption_n`. Debone-ok path does not emit this (those cards are not the local split).

### D3 — verdicts

- `figures_vml_unseen` — extract empty and `vml_unseen_n` > 0  
- `caption_stub_cards` — `stub_caption_n` > 0  

### D4 — local replay

`scripts/replay_docx_extract.py <docx-or-pdf>` calls the same functions and prints ASCII JSON only (`ensure_ascii=True`). No Gemini, no paper text, no `core.xml` creator. Windows cp949 consoles crash if those strings are printed.

### D5 — title tokens

Replay adds `info_title_class` (`empty` | `si_banner` | `code_like` | `text`), `info_title_char_n`, `stem_class`, `session_title_source` (`filename_stem` | `section_title`), `head_title_after_banner`, `title_verdict`. These are the ingest title path: metadata class and whether the session title would stay the filename stem. The title string itself is not emitted.

## Non-goals

- Product fix of VML extract / `Fig. S#` cards — that is [295](295-docx-vml-caption-split.md)  
- Version is the ship that includes the sensors; extract behavior is [295](295-docx-vml-caption-split.md)  

## Acceptance

1. Floor includes `sentence_split_done`; twins py+dart.  
2. `figure_extract_done` emit includes `vml_unseen_n`.  
3. Replay script exits 0 on a docx and names `figures_vml_unseen` when imagedata exists and figures are empty.  
