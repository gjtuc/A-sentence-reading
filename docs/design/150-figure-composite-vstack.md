# design/150 — Column-aware vstack composite (replace union clip)

**Version:** 0.3.71  
**Pipeline:** rich-v18  
**Depends:** [147](147-azure-layout-figures.md) · [149](149-azure-caption-composite.md) · [128](128-clip-column-width.md)

## Problem

Co–TiO₂ phone review (design/149 composite) showed three failure modes:

| Mode | Symptom | Root cause |
|------|---------|------------|
| Union bleed | Fig 1/2/6/7 include adjacent column body or tables | `clip = fig_rect \| cap_rect` in [`azure_layout.py`](../src/sentence_reading/pdf/azure_layout.py) |
| Caption loss | Fig 3–4: graph OK, caption nowhere (UI hides caption Text) | Azure/PyMuPDF miss + `_match_fig_caption_with_rect` caption-below only |
| Slot gap/dedup | Fig 5 missing; slot 7 repeats Fig 1 | Azure miss + `continue` on empty PNG + caption_key dedup |

Azure Layout v4 GA returns **separate** figure body and caption bboxes ([147](147-azure-layout-figures.md)). Bleed is post-processing, not detection.

## Product (locked)

- Figure carousel: **figure body + figure caption → one PNG**
- Table carousel: table body + table caption → one PNG (table vstack = Phase 2)
- UI: hide under-image caption Text when `figure_caption_in_image` ([149](149-azure-caption-composite.md))

## Architecture

```
Azure prebuilt-layout (detection SoT — body ∥ caption bbox)
  → resolve_figure_caption() (149 filter + PyMuPDF fallback)
  → _composite_figure_png() (NEW — column clamp + vstack; NO union)
  → fallback: Azure figure crop PNG → body-only clip
```

Reuses [`_column_x_range()`](../src/sentence_reading/pdf/extract.py) from design/128.

## Composite rules (figures)

1. **Column band** — anchor on `cap_rect` if present, else `fig_rect`; `_column_x_range(page.rect, anchor, bleed_frac=0.08)`.
2. **Full-width exception** (PDFFigures2 / PDFigCapX) — if anchor spans page midpoint **or** width > 55% of page width → use full content width (pad 6 pt each side), not single column.
3. **Clamp x** — intersect fig and cap rects with column band before clip.
4. **Vertical order** — sort clips by `y0` (caption usually below; caption-above supported via pairing fix).
5. **Vstack** — separate `_render_page_clip` per rect; PIL vertical stack; normalize width to max strip width; center narrower strip on white canvas.
6. **No union** — never `rect | cap_rect` for figure rasterization.

### Fallback chain (unchanged order)

1. vstack composite PNG  
2. Azure `get_analyze_result_figure` crop  
3. body-only `_render_page_clip(page, fig_rect)`

## Caption pairing (B1)

Extend `_match_fig_caption_with_rect()`:

- Caption **below** figure: `cap_rect.y0 - fig_rect.y1` (existing)
- Caption **above** figure: `fig_rect.y0 - cap_rect.y1` (mirror [`_pick_embed_for_caption`](../src/sentence_reading/pdf/extract.py))

## Tables

Azure table path still uses union clip in B1. Document same vstack pattern for Phase 2.

## Acceptance — Co–TiO₂ paper (manual QA after reanalyze)

| Slot | Must pass |
|------|-----------|
| Fig 1 | XRD stack + caption; **no** left-column Results/PXRD body |
| Fig 2 | Rietveld A/B + caption; **no** Tables 3–5 bleed |
| Fig 3–4 | Operando graph **and** caption visible in PNG |
| Fig 5 | Present at correct index (no skip to Fig 6) |
| Fig 6 | No right-column body in caption area |
| Carousel | Stable count; no duplicate Fig 1 phantom slot |

## Phase 2 (out of scope B1)

- [124](124-missing-figures.md) empty slots + honest placeholders  
- deep-zotero-style orphan caption recovery  
- Hungarian / IoU dedup  
- Azure **table** vstack composite  

## Re-ingest

Papers at **rich-v17** keep old figure PNGs until **re-upload or reanalyze**.

## Kill switches

| Env | Effect |
|-----|--------|
| `ASR_AZURE_LAYOUT=0` | PyMuPDF-only |
| `ASR_FIGURE_CAPTION_IN_IMAGE=0` | UI shows under-image caption Text |

## Code

- [`azure_layout.py`](../src/sentence_reading/pdf/azure_layout.py) — `_composite_figure_png()`, `_match_fig_caption_with_rect()` caption-above
- [`typography.py`](../src/sentence_reading/llm/typography.py) — `PIPELINE_VERSION = rich-v18`
