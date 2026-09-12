# 238 — OPEN_DOCUMENT pick + resume rescan

Version: **0.3.235** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · Depends [241](241-saf-tree-write-copy.md) for preferred copy · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- Resume / visible import → debounced `_scanPdfFolder` of **connected** tree.
- 「받은 PDF 고르기」→ **[248](248-pdf-import-downloads-inapp-browser.md)** in-app Downloads tree browse (not DocumentsUI `OPEN_DOCUMENT`). Legacy `pickDocuments` channel kept unused by this CTA.
- Preferred: `copyUriIntoTree` into grant (241) → rescan.
- Fallback if not writable: `enqueuePickedPdfs` bytes + honest snackbar.
- **Partial multi-pick:** when some copies succeed and some fail, enqueue **failed copies only**; `mode` = `copy_partial`; honest message (copied N · failed M → queue).
- No persistable single-file grant. Downloads **user-picked** tree grant OK ([248](248-pdf-import-downloads-inapp-browser.md)); no auto Downloads grant.

## Version

**0.3.235**
