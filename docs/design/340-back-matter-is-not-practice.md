# 340 — The journal's apparatus is not the paper

**Version:** 0.3.335 · Status: **locked**  
Closes the gap design/333 left · resolves ~10 of design/339's residual

## Why

design/333 built `strip_back_matter` to keep licence blocks, DOI lines, mastheads
and `How to cite this article` out of the **coverage denominator** — that is, the
metric already declared them "not practice text". Nothing applied the same knowledge
to the sentence stream, so the product handed the reader a Creative Commons licence
to say aloud while the metric refused to count it.

design/339 then met the same sentences from the other direction: about 10 of its 83
remaining speech defects were this text. Teaching TTS to pronounce
`http://creativecommons.org/licenses/by/4.0/` nicely is the wrong repair.

## Measured before changing anything

`agent-tools/backmatter.py` over the 2,366-sentence ten-paper corpus: **16 match, 0
false positives.** Every one is apparatus.

| paper | n | what they are |
|---|---|---|
| `srep41797` | 8 | Author Contributions, `Supplementary information … http://www.nature.com/srep`, `How to cite this article`, the DOI line, Publisher's note, the Creative Commons block and its "to view a copy" URL |
| `d4cs00527a` | 4 | the `Chemical Society Reviews rsc.li/chem-soc-rev` masthead, `Open Access Article.`, the `Received … DOI:` line |
| `science.1212858` | 2 | `Supporting Online Material www.sciencemag.org/…`, `DOI: … View the article online https://…` |
| `1-s2.0-S1385894724017960` | 2 | `Supplementary data … https://doi.org/…` and a DOI-carrying reference line |

## Locked

1. `is_back_matter_sentence` reuses design/333's own `_BACK_MATTER` and
   `_CHROME_LINE` patterns, so the denominator and the sentence stream now share one
   definition of practice text instead of disagreeing. A test asserts exactly that.
2. `_BACK_MATTER` gains the shapes the corpus produced:
   `supplementary information|materials|data`, `supporting information|online
   material`, `open access article`, `reprints and permissions`, `author
   information`.
3. **Judged on the sentence's own evidence, never on a section label.** This removes
   content, and design/335 is the record of what happens when a label is trusted for
   that. So `We thank A. Becker for helpful discussion.` stays: thanking people is
   prose, and only the apparatus heading is apparatus.
4. Markup cannot hide a URL — the predicate reads `plain_text` first.
5. `back_matter_dropped` on `IngestQuality`, in `to_dict()`, and as a
   `back_matter_dropped:N` warning. A deletion this chip makes is a deletion this
   chip reports.

## Not this chip

- Dropping the acknowledgement **section**. That needs the section label, which is
  the thing design/335 showed can be badly wrong, and the prose in it is at least
  real prose. If it should go, it should go on its own evidence.
- The non-Gemini sentence path (`split_into_sentences_detailed`) does not run this
  filter; the drop lives in `debone_sentences` so the count can reach
  `IngestQuality`.
- The 18 unit-grammar and 7 compositional-name speech defects from design/339.

## Test

`tests/test_design_340_back_matter.py` — all thirteen apparatus shapes the corpus
produced, seven body sentences that must survive including an acknowledgement
sentence and a citation in running text, markup hiding a URL, the count returned by
the drop, nothing reported when there is nothing to drop, the warning wiring, and the
assertion that the denominator and the stream agree.
