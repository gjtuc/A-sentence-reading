# 325 — The title bucket is not a bin, and the abstract has a heading

**Version:** 0.3.319 · Status: **locked**  
Amends [12](12-gemini-debone.md) · [31](31-reading-order.md) · [322](322-sentence-order-is-the-paper-order.md) · [167](167-debone-quality-guards.md)

## Why

Found by building a hand ground truth from the philosophy for five real papers,
then running the real logic and diffing (design/323 harness).

### A. `title` was a content sink that assembly deleted

`order_boxes` opens the first section as `title` and keeps appending to it until
`header_key` recognises a heading. `_assemble_sentences` kept only the **first**
`title` sentence and dropped the rest.

On a Wiley paper (`ChemistryOpen 2015, Jiang`) `header_key` matched only two
headings in the whole file, so the section split was:

| section | chars |
|---|---|
| **title** | **10,227** |
| experimental | 2,010 |
| acknowledgement | 2,267 |

The abstract, introduction, results and conclusion were all inside that 10,227
character `title` run, and every sentence after the first was thrown away. The
paper reached the reader as **13 sentences** with `source_coverage 0.209`.

No guard fired. design/167 only catches a chunk that returns *zero* sentences;
all five chunks reported ok. `coverage_low:0.21` was recorded, and the quality
banner is off, so the reader was told nothing.

### B. The abstract never opened a section

`header_key` accepted `abstract` and `abstract ` only. Journals run the heading
straight into the text:

- `Abstract−In order to increase...` (Springer / Korean J. Chem. Eng.)
- `ABSTRACT: A series of bimetallic...` (ACS)
- `A B S T R A C T` (Elsevier letter-spaces it)

Azure returns the abstract as one long paragraph, so the standalone-heading
length guard (`len(line) > 120`) rejected it before any match could be tried.

With no `abstract` section the abstract inherited whichever section was open.
On `s11814-008-0075-5` it was labelled **`experimental`** and placed **after**
the Experimental section — the abstract appeared in the middle of the paper.

## Locked

1. Only the first `title`-labelled item **in source order** is the title card.
   Later ones keep their text under `body` and keep their own position; they are
   never dropped and never hoisted with the title.
2. `header_key` decides the abstract run-in form **before** the length guard.
   `_ABSTRACT_RUN_IN` requires a separator (`-`, en/em dash, `−`, `:`, `·`)
   followed by text, so prose beginning with `Abstract`/`Abstracts` is not a
   heading.
3. A whitespace-collapsed exact match accepts `A B S T R A C T`.

## Measured effect

| paper | sentences | source coverage | order backward | abstract section |
|---|---|---|---|---|
| ChemistryOpen (Wiley) | 13 → **82** | 0.209 → **0.646** | — | — |
| Korean J. Chem. Eng. | 65 → 66 | 0.735 → 0.733 | 43.1% → 42.4% | none → **abstract** |
| ACS Catalysis | 288 → 290 | 0.678 → 0.675 | 10.5% → **6.9%** | none → **abstract** |

## Known limits

- **The abstract is labelled but not yet repositioned.** On
  `s11814-008-0075-5` the section list is now
  `title, introduction, experimental, abstract, results, conclusion`: the label
  is right, the place is still wrong. The full-width abstract block is ordered
  after the two-column body by `_read_page`, so source order puts it mid-paper.
  Fixing that means touching column ordering, which design/302 gates behind
  `azure_box_gate` being green. Next lead, not this chip.
- `header_key` still misses headings this chip did not enumerate. The title
  bucket no longer deletes them, so a miss now costs a label, not the text.
- Recall is still well under 1.0 on every paper measured (0.65–0.73). The rest
  is lost earlier, in `_drop_chrome` / `_keep_as_sentence` / `join_section_text`.

## Not this chip

- Per-chunk yield floor (a chunk returning 5% of its sentences still reads ok)
- `join_section_text` gluing the wrong neighbour across a column break
- Turning the ingest quality banner on
- Flattened super/subscripts changing reported values

## Test

`tests/test_section_flow.py` — `test_design_325_abstract_run_in_headings_open_a_section`,
`test_design_325_abstract_word_in_prose_is_not_a_heading`  
`tests/test_design_322_sentence_order.py` — `test_a_title_pinned_run_is_not_deleted`,
`test_a_mid_paper_title_label_is_not_hoisted_to_the_front`,
`test_only_the_first_title_card_is_a_title_but_the_rest_is_kept`
