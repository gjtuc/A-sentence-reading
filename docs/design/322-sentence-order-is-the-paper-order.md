# 322 — Stored sentence order is the paper's order

**Version:** 0.3.317 · Status: **locked**  
Amends [12](12-gemini-debone.md) · [31](31-reading-order.md) · [167](167-debone-quality-guards.md) · [321](321-extraction-boundary-census.md)

## Why

Only one sentence is ever on screen ([PRODUCT](../PRODUCT.md) invariant), so a
reader cannot notice that the paper was reordered. Trust in the order is forced,
not earned.

`_assemble_sentences` sorted by a section rank table, with source position only
as the tiebreak:

```python
order = _SECTION_ORDER.get(section, _SECTION_ORDER["body"])
decorated.sort(key=lambda t: (t[0], t[1]))
```

`collected` already arrives in chunk order, which is source order on both the
pinned (`<<<ASR_SECTION>>>` from `section_flow`) and unpinned paths, and the
front-matter retry writes back at the same index instead of appending. The rank
table therefore bought nothing and cost three things:

1. A journal that prints Methods after Discussion was shown Methods before
   Results. `section_flow` had the true order; assembly discarded it.
2. `methods` and `experimental` shared rank 3, so a stable secondary sort
   interleaved their chunks.
3. `body` ranked 7, after `conclusion` at 6. Any heading `header_key` did not
   recognise — including numbered headings via
   `re.match(r"^\d+\.\s+\S", line)` — moved its whole section past the
   conclusion.

Measured on the four real cached papers, backward source steps were
**61.2%**, **32.6%**, **15.4%**, **15.4%** of anchored sentences. The 61.2%
paper stored `methods, experimental, methods, experimental, methods` as five
alternating blocks (defect 2) and placed Results after Methods blocks that sit
later in the source (defect 1).

## Locked

1. Reading order is source order. Section is a label for the header and nav,
   never a sort key. `_SECTION_ORDER` is deleted.
2. The title card still leads, matching
   `title_replay.align_title_sentences`. Only the first title card survives.
3. `source_order_stats(raw_text, sentences)` anchors each sentence in the
   pre-filter text (design/321) by 6-gram and counts backward steps.
   Unanchored sentences are excluded, not guessed.
4. Warning `sentence_order_backward:<pct>` above 20%, and only with at least
   20 anchored sentences. Carried on the `extract_text` → `sentences_ready`
   handoff as `order_anchored_n` / `order_backward_n` / `order_backward_pct`.
5. `scripts/sentence_order_gate.py` cross-checks a stored session against its
   source PDF two ways: section-header order and sentence anchor monotonicity.
   ASCII JSON, counts and offsets only — never paper text (design/301).

## Known limits

- The PyMuPDF page join is itself an imperfect baseline for multi-column
  papers (design/31). A residual backward rate in the teens is expected and is
  why the warning threshold is 20%, not 0.
- Papers stored before this chip keep the old order until 재분석.

## Not this chip

- Turning the ingest quality banner on
- Per-sentence source offsets stored in `session.json`
- Reordering existing cached sessions in place
- `header_key` prefix and chrome-match drops (design/321 Not this chip)

## Test

`tests/test_design_322_sentence_order.py`
