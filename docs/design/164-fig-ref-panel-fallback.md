# 164 — Fig ref panel fallback (Figure 6C → Figure 6)

Modules: `fig_refs.py` · `fig_refs.js` · `fig_refs.dart` · reader chip row

## Problem

Body text `(Figure 6C)` / `Figure 6(D)` did not match `Fig. N` regex (`\d+[a-z]?` lowercase only). No jump chip while carousel has **Figure 6** composite.

## Rule (locked)

| Body ref | Chip label | Jump target |
|----------|------------|-------------|
| `Figure 6C`, `Figure 6(C)`, `Fig. 6D` | **Figure 6** | Base carousel slot `fig:6` |
| `Table 3B`, `Table 3 (B)` | **Table 3** | `table:3` |
| `Figure 1a` (lowercase sub-slot) | **Figure 1a** | Exact `fig:1a` when slot exists |

- Panel suffix: uppercase letter after digit **or** parenthesized letter `(C)`.
- One sentence with 6C + 6D → **one** chip (dedupe by `figure_index`).
- Fail-closed: no base slot → no chip.

## Version

**0.3.97** · no pipeline change
