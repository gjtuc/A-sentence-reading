# 169n — Library figure hydrate (post-ingest · honest progress)

**Version:** 0.3.141  
**Scope:** Figures only (no translate residual copy).

## Product

After ingest completes, library row shows `그림 x/N 받는 중` while the app
silently opens the cache and fills PNG bytes via existing `/figures/window`
(span=1). On full success the banner hides. Partial failure: `그림 K장 받지 못함`
(+ retry / dismiss). Never claim success when `image_src` is empty.

## Evidence (not shown in admin/user UI)

| kind | when |
|------|------|
| `figure_hydrate_start` | loop begins |
| `figure_hydrate_progress` | sample on filled growth |
| `figure_hydrate_done` | filled==total |
| `figure_hydrate_partial` | gaps remain |
| `figure_hydrate_abort` | silent open failed |
| `figure_window_req/res` | `source=hydrate_bg` vs `reader_prefetch` |

## Files

`figure_hydrate.dart` · `library_controller.dart` · `library_screen.dart` · kinds/floor
