# 344 — Measure lost text, not lost vocabulary

**Version:** 0.3.340 · Status: **locked**  
Corrects the instrument behind [321](321-extraction-boundary-census.md) · [330](330-coverage-denominator.md) · [333](333-coverage-denominator-correction.md) · [336](336-delete-only-what-you-can-name.md)

## Why

`coverage_ratio` compares **word lists**: the set of words in the source against the
set of words in the practice sentences. Measured on `catalysts-13-01171`, deleting one
158-character sentence moved it by **0.12 points** — 1 word of 811 vanished from the
paper, because every other word in that sentence appeared elsewhere.

So the instrument this project relies on to detect loss cannot see the scale of loss
that matters. Every "coverage 0.86" and every "no regression" in design/330 through
design/343 was read off it. design/335's 12,000 deleted characters were visible only
because they happened to contain words found nowhere else in the paper.

## Locked

`text_coverage(raw_text, sentences)` splits the source into sentence-sized fragments
and asks, of each one, whether it actually reached the reader.

1. A fragment needs **6+ words** to be worth checking.
2. A fragment counts as delivered when **half of its 5-word shingles** appear in the
   practice sentences. Half, not all: deboning legitimately removes citation markers,
   and a fragment can arrive split across two sentences. Both cases are tested.
3. The ratio is **character-weighted**, so a lost paragraph costs what a paragraph is
   worth.
4. It returns **the fragments themselves**. That is the point — a ratio says how much,
   a list says *what*.
5. Reported as `text_coverage` and `text_missing_n` in `IngestQuality.to_dict()`, and
   as `text_missing:<n>` / `text_coverage_low:<ratio>` warnings.
6. Wrapped so it can never break the ingest it is measuring.

**Apparatus is filtered out of the reported list.** The first run returned mastheads,
author name lists and RSC page stamps next to the real losses, which buries the
finding. A reported fragment must pass `looks_like_prose_line` and must not be
`is_back_matter_sentence` — the same two predicates the rest of the pipeline uses.
That halved the counts (`srep` 8 → 4, `d4cs` 39 → 24) and what remains is prose.

## Measured — every paper was losing sentences

| paper | word-list ratio | text ratio | prose fragments never delivered |
|---|---|---|---|
| `srep41797` | 0.894 | 0.961 | **4** |
| `cs5b00357` | 0.967 | 0.974 | **7** |
| `catalysts-13-01171` | 0.954 | 0.974 | **6** |
| `science.1212858` | 0.686 | 0.864 | **5** |
| `1-s2.0-S1385894724017960` | 0.864 | 0.879 | **16** |
| `s11814-008-0075-5` | 0.868 | 0.903 | **6** |
| `nl5b02080` | 0.889 | 0.905 | **3** |
| `d4cs00527a` | 0.910 | 0.957 | **24** |
| Adv. Mater. | 0.855 | 0.964 | **11** |
| ChemistryOpen | 0.800 | 0.776 | **17** |

The word-list ratio read 0.80 to 0.97 while **all ten** papers were dropping real
sentences. What is missing is not chrome:

```
cej    Starting materials of BaCO3 (Shanghai Macklin Biochemical Co., Ltd., 99.95 %) …
cej    The pristine BZY10 pellets were sintered at 1650 °C for 24 h …
cej    Water content was measured with Karl-Fisher titration …
srep   Because it could be conducted under mild conditions without the
srep   This observation was consistent with the XPS analysis result.
cata13 The formyl species (CHO*) is further decomposed to produce CO* and H*.
acscat where F_i (mol s⁻¹) is the molar flow rate of component i …
```

`1-s2.0-S1385894724017960` lost a run of **Experimental** sentences — starting
materials, sintering schedule, the SEM instrument, the titration method — and its
word-list ratio said 0.864.

## The ratio is not the finding

Note the text ratio reads *higher* than the word-list ratio on nine of ten papers.
That does not mean there is less loss than believed; it means the old number was
wrong in both directions. Words that appear only in figure captions or table cells
counted as lost prose, while whole lost paragraphs counted as nothing.

**The useful output is the list, not either ratio.** `text_coverage_low` exists for a
floor, but `text_missing:<n>` with the fragments in hand is what makes a loss
actionable.

## Not this chip

- Fixing the losses it found. They are now named; each needs its own cause traced.
- Surfacing the fragment text (not just the count) to the client.
- The fragment splitter cuts mid-sentence on list-like text (`81-1667), γ-Al2O3
  (JCPDS No.`), which produces a few unfair fragments.

## Test

`tests/test_design_344_text_ruler.py` — the blindness reproduced as a test rather
than asserted in prose; the text ruler seeing the same deletion; light editing and a
fragment split across two sentences still counting as delivered; nothing delivered
reading as nothing; an empty source not failing; short pieces not being fragments;
mastheads, page stamps and author lists filtered out of the report while real prose is
kept; the warning wiring; a clean paper saying nothing; and the ruler being unable to
break the ingest.
