# 443 — A caption under a running head, and a table carried onto the next page

## Ask

The Advanced Materials SI (`adma201600469-sup-0001-s1`) showed `Table 1 (missing)` in
the figure pane where Table S1 belongs.

## Cause

The SI prints `Submitted to` at the top of every page. Page 19 is landscape, and its
caption `Table S1.` starts 1pt under that head. Azure returned one paragraph for both,
`Submitted to Table S1. A detailed comparison…`. A caption is read from the start of
its text, so this one never read; the plan still made a Table S1 slot from Table S2's
number, and the slot stayed empty. The table itself came back as two unnumbered tables,
page 19 and page 20, beside four Azure tables found inside Figures S4 and S6.

## Change

**Head off the caption** (`layout_map.py`). A running head is a text of at most 60
characters printed alone in the top or bottom 15% of two or more pages. When a paragraph
starts with one and the rest reads as a caption, the box becomes that caption, and its
top moves down to the caption's own first line (PyMuPDF finds the label inside the box;
an upright page only). A head seen on one page, a short text repeated in the middle of
pages (a table's `NA`), or body text after the head stays a paragraph.

**Table carried over** (`caption_pairing.attach_carried_table_pages`). Once Table S1's
caption reads, the table captions run S1–S2 with no gap and design/357 holds every
unclaimed table back, so the part on page 20 (the CVD row) would vanish. This SI prints
no `(Continued)` there, so design/361 does not join it. A numbered table now takes the
unclaimed table body on the very next page when all of these hold:

- that page has no table caption;
- the held part ends in the bottom quarter of its page;
- the new part starts in the top quarter of its page;
- the left and right edges match within 24pt.

It repeats page by page, so a table over three pages takes all three.

## Result on the SI

Before: 19 entries, Table S1 `(missing)`, 6 unnumbered tables. After: 13 entries —
Figures S1–S11, Table S1 drawn from both pages, Table S2. The four tables inside
Figures S4 and S6 are held back as design/357 intends. A paper analysed before this
needs to be analysed again.

Left as is: the 6pt clip pad above the caption and above page 20's part catches the
bottom of the running head. The pad is shared by every crop.

Files: `src/sentence_reading/pdf/layout_map.py`, `src/sentence_reading/pdf/caption_pairing.py`,
`src/sentence_reading/pdf/extract_figures_v2.py`, `tests/test_design_443_running_head_caption.py`.
