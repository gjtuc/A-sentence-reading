# 241 — SAF tree write + stream copy

Version: **0.3.234** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · [238](238-pdf-import-open-document-pick.md)

## Locked

- Channel: `probeTreeWritable`, `copyUriIntoTree` (createFile + 64KiB stream, collision rename).
- Prefer WRITE persistable on `pickTree`; may require reconnect for old READ-only grants.
- Fail codes: `not_writable`, `create_fail`, `copy_fail`, `stale`, `too_large`.

## Version

**0.3.234**
