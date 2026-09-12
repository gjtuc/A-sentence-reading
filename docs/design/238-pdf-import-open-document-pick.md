# 238 — OPEN_DOCUMENT pick + resume rescan

Version: **0.3.235** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · Depends [241](241-saf-tree-write-copy.md) for preferred copy · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- Resume / visible import → debounced `_scanPdfFolder` of **connected** tree.
- 「받은 PDF 고르기」→ `ACTION_OPEN_DOCUMENT` (PDF), temp READ, `EXTRA_INITIAL_URI` = DocumentsContract **primary:Download** document ([247](247-pdf-import-downloads-bridge.md); not MediaStore).
- Preferred: `copyUriIntoTree` into grant (241) → rescan.
- Fallback if not writable: `enqueuePickedPdfs` bytes + honest snackbar.
- **Partial multi-pick:** when some copies succeed and some fail, enqueue **failed copies only**; `mode` = `copy_partial`; honest message (copied N · failed M → queue).
- No persistable single-file grant. No Downloads tree grant.

## Version

**0.3.235**
