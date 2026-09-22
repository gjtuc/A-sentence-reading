# 362 — Two label styles, and Scheme is not Figure

**Version:** 0.3.358 · Status: **locked**
Found while auditing the supplementary slots left over from [361](361-the-page-says-which-way-up.md) · extends [357](357-the-caption-list-is-the-paper.md) caption-first pairing

## Why

### The audit tool was wrong before the product was

`agent-tools/folder_audit.py` computed each file's `role` (`si` or `main`) from its name
and never handed it to `build_slot_plan`. Every supplementary PDF was paired as if it
were a main paper, where `Figure S1` is discarded on purpose — a main paper has no
figure S1. So 13 SI files reported a caption list of **zero** and their whole contents
were filed as nameless carousel leftovers.

Re-running the same 13 files with the flag the product passes:

| | as main | as supplementary |
|---|---|---|
| slots from captions | 53 | 169 |
| filled | 9 | 115 |
| nameless leftovers | 249 | 176 |

Twelve of the 13 were already correct in the product. **Fix the ruler before the thing
being measured.**

### Nature writes the S as a word

One file got *worse* with the flag: `41929_2026_1513_MOESM1_ESM` (Nature Catalysis SI,
87 pages) went from 9 filled to 0, and 42 empty slots to 52.

A supplementary number is printed two ways:

| house | caption | parsed |
|---|---|---|
| ACS, RSC, Elsevier | `Figure S1.` | `fig:s1` |
| Nature | `Supplementary Fig. 1.` | `fig:1` — the word was dropped |

The slot maker named its slots `fig:s1..fig:s33` and `table:s1..table:s19`. The caption
reader reported `fig:1..fig:33`. `fig:1` is not `fig:s1`, so **not one of the 52 slots
ever met its caption**, on a paper that prints every caption on its own line. 52 empty
slots, 176 nameless leftovers.

Two places had to learn the word: `caption_key` in `fig_refs.py`, which names the
caption, and `_slot_label_pattern` in `caption_pairing.py`, which is what the global
search matches a box's opening against.

The same reading fixed the main article. `s41929-026-01513-y` cites
`Supplementary Fig. 13` in its body, which used to parse as `fig:13` and built the main
paper **13 phantom figure slots that could never be filled**. They are gone.

### A scheme is not a figure

`slot_key_from_caption_key` folded `scheme:N` into `fig:N`. Every journal that prints
both numbers them separately, so `Scheme 1` and `Figure 1` are two different pictures —
and they were stacked into one slot and rendered as one composite. Three of 88 papers
print both: `d4se00467a`, the d-band XAS review, and Adv. Mater. 2024 He. All three
collided on number 1.

This is the same principle as [357](357-the-caption-list-is-the-paper.md): the paper's
own caption tells us what a picture is. It printed the word `Scheme`, so the word is
read.

## Locked

### The supplementary word carries the S

```
Supplementary Fig. 1   ->  fig:s1
Supporting Figure 2    ->  fig:s2
Supplemental Table 5   ->  table:s5
Figure S1              ->  fig:s1   (unchanged)
Fig. 2                 ->  fig:2    (unchanged)
```

Measured over the 88 PDFs: **no main-paper caption prints any word in front of its
number**, so honouring this word cannot move a main figure into a supplementary slot.
Only `41929_2026_1513_MOESM1_ESM` prints it, on all 40 of its caption boxes.

`_slot_label_pattern` accepts the bare number **only** when the word is there:
`Supplementary Table 1` must never be handed to the main paper's `table:1`.

### Scheme has its own slot family

- `SLOT_KINDS = ("fig", "scheme", "table")`, `SLOT_KIND_ORDER` = 0, 1, 2 — the carousel
  order design/92 already sorted captions by
- a scheme's picture is a `figure_body` (`slot_body_kind`), so it is searched for above
  its caption and among figures, never among tables
- `slot_kind_word` labels it `Scheme N`, and `slot_unnumbered_caption` names it in the
  same shape as the other two kinds
- `_index_for_key` tries `scheme:N` across every figure first, and only then the legacy
  `fig:N` — papers cached before this stored their schemes there. Trying both at once
  would hand `Scheme 1` the picture that belongs to `Figure 1`

## Measured over the 95-file folder

| | design/361 | design/362 |
|---|---|---|
| slots filled | 745 | **906** |
| slots empty | 56 | **0** |
| slots partial | 264 | **16** |
| nameless carousel entries | 260 | **11** |
| slots that exist at all | 1065 | 922 |
| caption with no picture | 3 | 5 |
| bodies held by the caption list | 275 | 359 |

`slot_n` falls because the phantom `Supplementary Fig. N` slots are gone. `pdf_held`
rises by the same images that used to be shown as nameless entries: on the Nature SI
alone, 116 journal-furniture boxes are now held instead of 119 being shown.

Text coverage (`0.4603` minimum) and order (`0` backward) are unchanged — this design
does not touch the sentence path.

The two extra `caption with no picture` are `cs9b00733_si_001` `fig:s2` (the file is in
the folder twice). It is not a new loss: that paper previously had no caption slots at
all, so the gap had nothing to be visible against.

## Not this chip

- **`cs9b00733_si_001` `fig:s2`, and `fig:4` / `fig:1` / `fig:6` on three main
  papers** — 4 distinct captions with no picture found, out of 922 slots. Layout edit.
- **Supplementary `Scheme S1`** — the key is built and the pattern matches, but no
  file in the folder prints one, so it is unmeasured.
- **`Extended Data Fig. 1`** — Nature's third numbering. It is neither the main figure
  1 nor supplementary figure 1. No file in the folder prints one; inventing a rule for
  it now would be guessing.

## Files

- `src/sentence_reading/fig_refs.py` — `_SUPP_WORD`, `_supp_num`, `_slot_wants`
- `src/sentence_reading/pdf/slot_plan.py` — `SLOT_KINDS`, `SLOT_KIND_ORDER`,
  `slot_body_kind`, `_scan_max_numbers` returns per-kind tops
- `src/sentence_reading/pdf/caption_pairing.py` — `_slot_label_pattern`
- `src/sentence_reading/pdf/composite.py` — `slot_kind_word`
- `src/sentence_reading/pdf/extract.py` — `_slot_sort_key`
- `src/sentence_reading/pdf/extract_figures_v2.py` — scheme labels, orphan crop
- `agent-tools/folder_audit.py` — passes `role`, runs `attach_continued_pages`
- `tests/test_design_362_two_label_styles.py` — 19 tests
