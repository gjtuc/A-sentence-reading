# 439 — Every figure in a list gets a chip

## Ask

A sentence said "Figs. 5, 7 and 8", and only a "Figs. 5" chip appeared. Figures
7 and 8 should get their own chips.

## Change

After one kind word, every number in the list is read as its own ref, at its own
place in the sentence:

- "Figs. 5 and 6", "Figs. 5, 7 and 8", "Figs. 5, 7, and 8", "Figs. 5 & 6".
- "Figs. 5–7" (en dash, em dash or hyphen) becomes 5, 6 and 7. A range of more
  than 12 is not expanded.
- "Tables 2 and 3", "Schemes 1 and 2". The plural "Tables" was not read at
  all before.
- "Figs. S1 and S2", and "Figs. 5a and 6b", which match figures 5 and 6 as a
  single "Fig. 5a" does.

The extra chips are labelled "Fig. 7", "Table 3" and so on. As before, only refs
that match a figure in the paper get a chip.

## Numbers that are not figures

- A singular kind word followed by a comma and one more number is a count:
  "In Fig. 3, 4 samples" stays Fig. 3. The second number is kept only when the
  list goes on ("Fig. 3, 4 and 5"), or when it ends at `)`, `.`, `;`, `]`. A
  plural ("Figs. 3, 4") always keeps it.
- A dash that is not a small rising range ends the list: "Fig. 2–200 nm" stays
  Fig. 2.
- A number glued to letters ("Fig. 2nd") is not a ref.

## Server

`fig_refs.py` follows the same rule, because the server's first-chip sentence
(design/183) must agree with the phone's chips. On the server, "Supplementary
Figs. 1 and 2" makes both numbers supplementary (design/362).

Files: `mobile/lib/api/fig_refs.dart`, `src/sentence_reading/fig_refs.py`,
`mobile/test/fig_refs_test.dart`, `tests/test_fig_refs.py`.
