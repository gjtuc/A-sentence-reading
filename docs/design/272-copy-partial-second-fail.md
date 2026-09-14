# 272 — Multi-pick copy_partial second-failure honesty

Version: **0.3.264** · Status: **locked**  
Amends [238](238-pdf-import-open-document-pick.md) · [241](241-saf-tree-write-copy.md)

## Locked

1. Keep enqueue-failed-copies-only (238).
2. Track `read_failed` and `enqueue_skipped`; do **not** overwrite `too_large` with bare `copy_partial`.
3. Snackbar when `enqueued < failed` states read/queue shortfall honestly.
4. Evidence on `pdf_import_pick_done`: `failed`, `read_failed`, `enqueue_skipped`.

## Kill

Revert.
