# design/151 — Layout map, slot carousel, Gemini pairing, overlay editor

**Version:** 0.3.73  
**Pipeline:** rich-v20  
**Depends:** [150](150-figure-composite-vstack.md) · [124](124-missing-figures.md) · [147](147-azure-layout-figures.md)

## Problem

Co–TiO₂ QA on **rich-v18** still shows column bleed, carousel index ≠ paper Fig number, tables interleaved with figures, and missing Fig 5. Root cause: Azure output sorted by page position + caption-key dedup, not slot order.

## Product (locked)

| Rule | Detail |
|------|--------|
| Figure caption | **Always below** figure body |
| Table caption | **Always above** table body |
| Carousel order | **Figure 1→N**, then **Table 1→M** |
| Missing numbers | **Empty slots** with honest placeholders ([124](124-missing-figures.md)) |
| Refill | **2-pass** global search for `"Figure N"` / `"Table N"` |
| Residual errors | **Overlay editor** — tap bbox → O/X → assign/replace |
| Supplementary | **Deferred** — `is_supplementary_label()` stub returns false |

## Architecture

```
Azure prebuilt-layout (once)
  → layout_map.json (paragraphs, figures, tables boxes)
  → slot_plan.json (fig:1..N, table:1..M ordered slots)
  → caption_pairing (strip + Gemini classify + distance fallback)
  → composite.py vstack PNG (figures + tables)
  → 2-pass refill
  → Figure[] in slot order (Azure v2 — no PyMuPDF orphan append)
```

User correction: mobile overlay → `figure_edit` API → re-render slot PNG.

## Data model

### `layout_map.json`

- `pages[]`: `{ page_index, width_pt, height_pt }`
- `boxes[]`: `{ id, page_index, kind, rect, text?, azure_ref?, used_by_slot? }`
- `kind`: `figure_body | table_body | figure_caption | table_caption | paragraph`

### `slot_plan.json`

- `slots[]`: `{ key, kind, n, status, body_box_id?, caption_box_id?, caption_text? }`
- `status`: `empty | partial | filled | user_confirmed`
- Ordered: all `fig:*` by n, then all `table:*` by n

### `Figure.slot_key`

Optional carousel ↔ slot mapping (`fig:3`, `table:2`).

## Caption pairing

1. **Primary strip** — figure: search **below** body; table: search **above** body; x-width filter 0.5–1.2× body width.
2. **Gemini classify** — up to 5 candidates per slot (`caption_classify.py`).
3. **Distance fallback** — below/above weighted; require label number match.
4. **Dedup** — `used_by_slot` on assigned boxes (no Hungarian IoU).

Figure caption-above search removed from primary path (design/150 fallback only if env enables).

## Composite

- [`composite.py`](../src/sentence_reading/pdf/composite.py) — column clamp + vstack (figures and tables).
- `empty` slot → placeholder PNG + `Figure N (missing)` / `Table N (missing)`.
- `partial` → body-only PNG.

## API (`figure_edit`)

| Route | Purpose |
|-------|---------|
| `GET /api/cache/papers/{id}/layout_map` | Overlay boxes |
| `GET /api/cache/papers/{id}/slot_plan` | Slot statuses |
| `POST /api/cache/papers/{id}/slots/{slot_key}/assign` | `{ body_box_id?, caption_box_id? }` → `user_confirmed` |
| `POST /api/cache/papers/{id}/slots/{slot_key}/render` | Re-vstack → update figure PNG |

Reanalyze **preserves** slots with `user_confirmed: true`.

## Mobile overlay UX

Entry: long-press figure panel → `FigureEditScreen`.

1. Slot list (Fig 1..N, Table 1..M) with status badges.
2. Select slot → prompt body/caption selection.
3. PDF page + colored bbox overlay (`layout_overlay.dart`).
4. Tap box → bottom sheet: preview + **✓ Insert / ✕ Cancel**.
5. On ✓ → assign + render → refresh reader carousel.

## Version / cache invalidation

- Pipeline **rich-v20** in [`typography.py`](../src/sentence_reading/llm/typography.py)
- App **0.3.73** in [`app.py`](../src/sentence_reading/api/app.py), [`config.dart`](../mobile/lib/config.dart)
- Papers at rich-v18 keep old PNGs until reanalyze

## Acceptance — Co–TiO₂ (manual QA)

| Check | Must pass |
|-------|-----------|
| Carousel order | All figures before all tables |
| Slot index | Slot i label matches Fig/Table number |
| Empty slots | Missing numbers show honest placeholder |
| Overlay | User can assign body/caption to empty slot |

## Out of scope

- Supplementary Fig/Table filtering (stub only)
- Web overlay editor
- Hungarian IoU dedup

## Code

- [`layout_map.py`](../src/sentence_reading/pdf/layout_map.py)
- [`slot_plan.py`](../src/sentence_reading/pdf/slot_plan.py)
- [`caption_pairing.py`](../src/sentence_reading/pdf/caption_pairing.py)
- [`caption_classify.py`](../src/sentence_reading/llm/caption_classify.py)
- [`composite.py`](../src/sentence_reading/pdf/composite.py)
- [`extract_figures_v2.py`](../src/sentence_reading/pdf/extract_figures_v2.py)
- [`figure_edit.py`](../src/sentence_reading/api/figure_edit.py)
- [`layout_overlay.dart`](../mobile/lib/widgets/layout_overlay.dart)
- [`figure_edit_screen.dart`](../mobile/lib/screens/figure_edit_screen.dart)
