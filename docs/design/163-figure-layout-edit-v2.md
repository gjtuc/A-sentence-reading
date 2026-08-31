# 163 — Figure layout edit v2

**Version:** 0.3.99  
**Depends:** [151](151-layout-map-slot-carousel.md) · [164](164-fig-ref-panel-fallback.md)

## Product (locked)

| Rule | Detail |
|------|--------|
| PDF background | `page_preview` API + phone stash |
| Multi-select | Union bbox one crop per role (not per-box vstack) |
| Body+caption | Slot-level vstack (fig: body then caption; table: reverse) |
| Modes | Pan · Select · Crop (manual box) |
| Local session | Edit in memory; `POST figure_edit/commit` on save/exit |
| Stash lifecycle | `paper_edit_stash/{cache_id}`; purge on delete/logout |

## API

| Route | Purpose |
|-------|---------|
| `GET/HEAD …/source` | Phone stash fill |
| `GET …/page_preview?page_index=N` | Edit background PNG |
| `POST …/figure_edit/commit` | multipart manifest + slot PNGs |

## Mobile modules

- `paper_edit_stash.dart` · `figure_edit_session.dart`
- `figure_edit_geometry.dart` · `figure_edit_compositor.dart`
- `figure_edit_screen.dart`

## slot_plan v2

`body_box_ids[]` · `caption_box_ids[]` (legacy single-id migrated on load)
