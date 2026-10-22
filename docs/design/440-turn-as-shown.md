# 440 — The turn is read in the page as shown

Extends [361](361-the-page-says-which-way-up.md).

## Ask

`1-s2.0-S0008622310008997` page 8 prints Table 3 and Fig. 10 on a page the viewer
shows in landscape. Fig. 10 was cropped well and turned, but came out upside down.

## Why

That page carries `/Rotate 90`. design/361 measured papers whose sideways pages all
had `/Rotate 0`, so it never had to choose a space. There are two:

- PyMuPDF reports each line's `dir` and `bbox` in the page **as stored**.
- `get_pixmap(clip=...)` renders the page **as shown**, after `/Rotate`, and Azure's
  boxes are in that space too. That is why the crop itself was right.

Fig. 10's caption is `(1, 0)` as stored. As shown it reads down the sheet, so it
needs a counter-clockwise turn. Read in the stored space, an Azure box in shown
coordinates matched the wrong lines, so the crop was turned clockwise: 90 + 90 = 180.

## Change

`page_turn._shown_lines` maps every line's `dir` and `bbox` through
`page.rotation_matrix` before counting, so `page_turn` and `rect_turn` answer in the
space the crop is cut from. A page with `/Rotate 0` is unchanged.

`_slot_turn` recomputes the turn of a `/Rotate` page instead of reading
`LayoutMap.pages[i]["turn"]`, because a map stored before this change read that page in
the stored space. The figure layout editor re-renders from stored maps.

## Measured

36 papers in the doctor's folder, 2 pages with `/Rotate 90`:

| page | stored dirs | shown dirs | before | after |
|---|---|---|---|---|
| `1-s2.0-S0008622310008997` p.8 | `(1,0)` 87, `(0,-1)` 73 | `(0,1)` 87, `(1,0)` 73 | Fig. 10 turned cw, upside down | Fig. 10 turned ccw, upright |
| `acsaem.9b01599` p.27 | `(0,-1)` 49 | `(1,0)` 49 | whole page read as `cw` | upright, no turn |

Seen with the eye: the Fig. 10 crop after the change has panels (a)–(c) upright and
the caption under them.

Old figures stay as they were until the paper is analysed again.

Files: `src/sentence_reading/pdf/page_turn.py`,
`src/sentence_reading/pdf/extract_figures_v2.py`,
`tests/test_design_440_shown_page_turn.py`.
