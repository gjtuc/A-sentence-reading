# 238 — OPEN_DOCUMENT pick + resume rescan

Version: **0.3.234** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · Depends [241](241-saf-tree-write-copy.md) for preferred copy

## Locked

- Resume / visible import → debounced `_scanPdfFolder` of **connected** tree.
- 「받은 PDF 고르기」→ `ACTION_OPEN_DOCUMENT` (PDF), temp READ, optional `EXTRA_INITIAL_URI` Downloads hint.
- Preferred: `copyUriIntoTree` into grant (241) → rescan.
- Fallback if not writable: `enqueuePickedPdfs` bytes + honest snackbar.
- No persistable single-file grant. No Downloads tree grant.

## Version

**0.3.234**
