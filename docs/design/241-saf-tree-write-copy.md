# 241 — SAF tree write + stream copy

Version: **0.3.235** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · [238](238-pdf-import-open-document-pick.md) · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- Channel: `probeTreeWritable`, `copyUriIntoTree` (createFile + 64KiB stream, collision rename).
- Prefer WRITE persistable on `pickTree`; may require reconnect for old READ-only grants.
- **Proactive** `probeTreeWritable` on grant load / connect (`refreshPdfFolderWritable`); banner when `pdfFolderWritable == false`.
- Fail codes: `not_writable`, `create_fail`, `copy_fail`, `stale`, `too_large`.

## Version

**0.3.235**
