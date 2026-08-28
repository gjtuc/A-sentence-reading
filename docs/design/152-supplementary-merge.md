# design/152 — Supplementary 분리·합치기·Picker/Fig칩

**Version:** 0.3.78  
**Pipeline:** rich-v24  
**Depends:** [151](151-layout-map-slot-carousel.md) · [28](28-fig-ref-chip.md) · [49](49-cite-display-clean.md)

## Problem

Main PDF and Supplementary Information (SI) share the same paper title but must be analyzed and read separately until the user merges them. Cache dedup by `title_key + source` alone overwrites two PDFs with the same title. Body cites like `Fig. S2` must stay hidden until SI figures are merged into the main reader session.

## Product (locked)

| Rule | Detail |
|------|--------|
| Auto role | SI head: `Supplementary Information`, `Supporting Information`, etc. → `doc_role=supplementary` |
| Library tags | `메인` · `보충` · `메인+서플먼터리` (merged) |
| Dedup key | `title_key + source + doc_role` |
| Merge button | Main entry only; both main+SI `ingest_status=ok`; same `title_key` |
| Merge effect | SI sentences + figures **append** to main session; SI hidden in library |
| Sentence section | SI → `section=supplementary` → Picker **Supplementary N / M** |
| Figure slots | SI → `fig:s1`, `table:s1` (S prefix in slot_key) |
| Fig chips | `Fig. S2` hidden until merged; bare `S2` when merged |
| Picker | Merged: Supplementary section + Figure S2 / S7 wheels |

## Architecture

```
Upload PDF/DOCX
  → extract text
  → detect_doc_role(head) → main | supplementary
  → ingest (debone, figures, slot_plan with S slots if SI)
  → save_paper_session(doc_role=…)
  → library list (pair by title_key, tags)

User: Merge on main
  → POST …/merge-supplementary
  → append sentences/figures + copy PNGs
  → main doc_role=merged, SI hidden_in_library
  → reader: Picker + Fig S chips
```

## Data model

### Index entry

- `doc_role`: `main` | `supplementary` | `merged`
- `ingest_status`: `ok` | `failed` | `running`
- `paired_cache_id`, `merged_supplementary_id`, `hidden_in_library`
- API computed: `library_tag`, `can_merge_supplementary`

### Session JSON

- `doc_role`, `supplementary_merged`, `supplementary_cache_id`, `merge_revision`

## API

| Route | Purpose |
|-------|---------|
| `GET /api/cache/papers` | `doc_role`, `library_tag`, `can_merge_supplementary` |
| `POST /api/cache/papers/{main_id}/merge-supplementary` | Append SI into main |

## Modules

- `pdf/supplementary_detect.py` — head SI marker
- `cache/paper_cache.py` — dedup + pairing + merge save
- `api/supplementary_merge.py` — merge handler
- Mobile: `paper_models.dart`, `library_screen.dart`, `reader_nav_labels.dart`, `fig_refs.dart`

## Version pin

Reanalyze required after rich-v24 for SI slot keys and doc_role on legacy caches.
