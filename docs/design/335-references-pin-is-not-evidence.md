# 335 — A `references` pin is not evidence that text is a reference list

**Version:** 0.3.328 · Status: **locked**  
Amends [263](263-bibliography-not-practice.md) · [332](332-headingless-reference-list.md) · resolves the Sci Rep residual from [333](333-coverage-denominator-correction.md)

## Why

`_process_chunk_with_guard` deleted a chunk outright when its section pin said
`references`:

```python
if pinned:
    pairs = [] if pinned == "references" else [...]
```

The pin comes from Azure's section flow. Nothing checked it against the chunk's own
text, so wherever the reference run started too early, every character after it was
discarded. On `srep41797` one `references` pin covered **23,090 of 45,968**
recovered characters — five consecutive chunks:

| chunk | chars | reference-like lines | years | mean line |
|---|---|---|---|---|
| 7 | 5,000 | 0% | 0 | 999 |
| 8 | 5,000 | 0% | 1 | 1,249 |
| 9 | 5,000 | 50% | 6 | 498 |
| 10 | 5,000 | 89% | 29 | 177 |
| 11 | 3,090 | 94% | 16 | 191 |

Chunks 10 and 11 are the bibliography. Chunks 7 and 8 carry no enumeration, no
years and thousand-character lines: they are body paragraphs. Roughly 12,000
characters of the paper were deleted.

Two things made it invisible:

- The splitter proves the content was there. Fed chunks 7, 8 and 9 directly,
  `fallback_split_chunk` returns 27, 32 and 42 sentences.
- The quality record blamed the model. `chunk_kind` reads the text and called the
  chunks `substantive`; the pin then emptied them; `build_ingest_quality` saw a
  substantive chunk with zero sentences and reported
  `chunks_failed: [7, 8, 9]` / `partial_debone:7/12`. A deliberate deletion was
  reported as an LLM failure, which is the one place nobody would look for missing
  body text.

## Where the pin comes from

`_retag_bibliography_runs` (design/332) sets `in_refs = True` after two
consecutive bibliography lines, and the flag is **sticky**: the `else` branch
resets the run counter but not `in_refs`, so every later box is `references` until
an explicit heading appears. Many papers have no detected heading after their
bibliography, so the label runs to the end of the document. `srep41797` shows it
directly — `pin_order` ends `[... 'acknowledgement', 'references']`.

Combined with Azure placing body boxes after the bibliography (the
`azure_reading_order` warning), the chain is:

1. Azure's reading order moves body boxes past the reference list.
2. The sticky `in_refs` paints them `references`.
3. The debone gate deletes them unverified.

This chip fixes step 3 and contains the harm. Step 2 is recorded in **Not this
chip**: unsticking the label there risks re-opening design/332, and the rescued
prose is already recovered. The cost of leaving it is that rescued prose is
labelled `body` rather than its true section.

## Locked

1. **One shared predicate.** `cite_refs.is_bibliography_line` judges a line on its
   own evidence: `[n]`/`(n)` enumeration, or `n.` enumeration **plus** a year,
   `et al`, or a DOI, and at most 600 characters. `3. Author, A. ... 2019` is a
   reference; `2. Add the acid slowly` is a procedure step.
   `section_flow._is_bibliography_line` delegates here.
2. **Line-level deletion, not chunk-level.** Inside a `references`-pinned chunk,
   `split_off_bibliography_lines` keeps the lines that are running prose and drops
   the rest. The run boundary lands mid-chunk, so chunk 9 keeps its prose half.
3. **Surviving lines must be prose.** `looks_like_prose_line` requires 60+
   characters, 8+ alphabetic words, and under 18% digits. This kills the wrapped
   tail of a reference entry (`Nature 512, 22-28 (2014).`), page footers, and
   headings. Without it, chunk 10's strays were rescued.
4. **`PIN_RESCUE_MIN_SHARE = 0.20`.** The rescue is refused unless the surviving
   prose is a fifth of the pinned chunk. Set low on purpose: deleting body prose
   is the worse failure, and there is no downstream net —
   `filter_bibliography_sentences` runs only for `doc_role == "supplementary"`.
4b. **`REF_SIGNAL_DENSITY_MAX = 2.0`**, checked on the surviving region as a
   whole. MDPI and ACS split one reference across boxes: the author list becomes a
   long, low-digit, numberless line that passes every per-line test. Only the
   aggregate exposes it. `reference_signal_density` counts `[CrossRef]`/`[PubMed]`
   /DOI markers, surname-plus-initials runs, and year-volume-page triples per 1000
   characters, and needs 3+ hits before scoring at all. A **bare year is not
   counted** — body prose says `since 2015`, so years cost false refusals and add
   nothing to the separation.
5. **Rescued prose is `body`.** It is not a reference entry, so it is not labelled
   one.
6. **An honored pin keeps `kind="references"`**, so a deliberate drop reads as a
   drop and never as a failed substantive chunk.
7. **The deletion is reported.** `bib_chars_dropped` counts what was removed as
   bibliography; `references_pin_rejected` lists the chunks where the pin was
   overruled, also as `references_pin_rejected:<i>` warnings.

design/263 is intact: a genuine bibliography chunk still yields no practice
sentences, and the model is not even called for it.

## Measured — `srep41797`

| | before | after |
|---|---|---|
| sentences | 112 | **199** |
| `source_coverage` | 0.437 | **0.657** |
| `coverage_ratio` | 0.437 | **0.867** |
| `body_sentence_count` | 16 | **93** |
| `chunks_failed` | `[7, 8, 9]` | `[]` |
| `chunks_ok` | 7/12 | **12/12** |
| `bib_chars_dropped` | not measured | 6,749 |
| `references_pin_rejected` | — | `[7, 8, 9]` |

Chunk 10 is correctly **not** rescued.

## Measured — how widespread the deletion was

Body prose recovered, on the three papers where a pinned region really was prose:

| paper | publisher | sentences | `source_coverage` | rescued chunks |
|---|---|---|---|---|
| `srep41797` | Nature | 112 → **199** | 0.437 → **0.657** | 7, 8, 9 |
| `science.1212858` | Science | 53 → **66** | 0.476 → **0.615** | 1, 2, 3, 4 |
| `1-s2.0-S1385894724017960` | Elsevier | 148 → **150** | 0.580 → 0.591 | 16 |

`science.1212858` had four of its five chunks deleted.

The drop that design/332 produced on `catalysts-13-01171` (0.788 → 0.545) and
Adv. Mater. (0.850 → 0.676) was read at the time as references being correctly
excluded. It was — those regions are genuine bibliography. What design/332 also
did was hand the deletion gate far more text to delete unverified, which is what
made the gate's missing check expensive.

## The density gate is the load-bearing test, not a refinement

`catalysts-13-01171` first came back at 392 sentences — and `ungrounded_count`
rose to **62**, every one of them in the rescued tail, shaped like
`Catalysts 2023, 13, 117. [CrossRef]` and `Author, A.B.; Smith, C.D.`. MDPI's
split entries passed every per-line test.

The 10-paper audit (`agent-tools/pinaudit.py`, 32 pinned chunks) shows this is not
an MDPI quirk. On RSC and Wiley the per-line predicate sees **nothing**:

| paper | chunks | reference-like lines | density | correct call |
|---|---|---|---|---|
| `d4cs00527a` (RSC) | 34–39 | **0.0%** | 36–50 | drop |
| `catalysts-13-01171` (MDPI) | 11–14 | **0.0%** | 7–17 | drop |
| Adv. Mater. (Wiley) | 16–18 | 73–95% | 6–68 | drop |
| `srep41797` | 7–9 | 0–50% | **0.00** | rescue |
| `science.1212858` | 1–4 | 0–77% | 0.00–1.94 | rescue |

Without the density check, RSC's ~29,000 characters of bibliography across six
chunks would have become practice sentences, with `is_bibliography_line` reporting
0.0% on every line.

## Where the threshold comes from

Across all 32 pinned chunks:

- highest **true body** region: **1.94**
- lowest **true reference** region: **6.11**
- between them: nothing

Any threshold from 2.0 to 5.0 decides all 32 chunks identically. `REF_SIGNAL_DENSITY_MAX`
is **3.5**, the geometric middle, giving 1.8x headroom below and 1.75x above.
2.0 shipped first and left only 3% under it.

The 1.94 case is instructive: it is `science.1212858`, and the score comes from
`Acknowledgements: we thank A. Becker, B. Cho, C. Muller …`. Thanked names match
the author-initials pattern. The region is prose — its kept lines are 339 to 1,255
character paragraphs at density 0.00 — so the near miss was a correct call for the
wrong reason, and the threshold now has room for it.

Signal weights are not tunable by taste either. Dropping the initials term was
considered and rejected: on RSC and Wiley the marker term is **0.00** and initials
is the only signal present.

## The order metric was clean because the evidence was deleted

Restoring the text moved `sentence_order_backward` from **1.7% to 40.4%**. The
rescued prose anchors early in the raw text but Azure placed it after the
acknowledgements, and `recover_warnings` already said `azure_reading_order`.

The order looked perfect only because the misordered content was being thrown
away. That is a reporting result, not a regression: the paper's flow is genuinely
scrambled and now says so. Repairing the order is design/301 / design/302 work
(`scripts/azure_box_gate.py`), not this chip.

## Not this chip

- **Unsticking `in_refs` in `_retag_bibliography_runs`.** The root cause is known
  and written above. Exiting the references region on prose risks re-opening
  design/332 for publishers whose entry numbers sit in a separate box, and the
  content is already recovered at the gate. The residue is that rescued prose is
  labelled `body`: `science.1212858` comes out `body_ratio 1.0`.
- Azure reading order (40.4% backward on `srep41797`) — design/301 / design/302
- `acknowledgement`, `Author Contributions:` and `Supplementary Materials:` text
  still becoming practice sentences when they are not inside a pinned region
- A numbered bibliography that `cut_bibliography_for_sentences` does not cut still
  sits in the coverage denominator (carried from design/333)

## Test

`tests/test_design_335_references_pin.py` — the predicate against four entry
shapes, procedure steps and long numbered paragraphs; the split on mixed text; a
genuine bibliography still dropped without calling the model; prose swallowed by
the pin surviving as `body`; the mixed chunk keeping its prose half; wrapped
reference tails, footers and headings refused; the 89%-references chunk not
rescued by strays; MDPI split entries refused by density end to end; years in body
prose not refusing a rescue; other pins untouched; and the reporting fields.
