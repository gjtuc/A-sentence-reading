# 227 — PDF import 「최근」 section label

Version: **0.3.226** · Status: **locked**  
Depends: [226](226-pdf-folder-import-browser.md) · [223](223-library-upload-picker-investigation.md)

## Locked

| Include | Exclude |
|---------|---------|
| Visible `최근` label above `_RecentStrip` on `PdfImportScreen` | Changing recent tap / prefs schema |
| Align copy with 223 sheet 「최근」 | Title/SI on recent chips (no durable URI) |

## INVARIANT

- Strip still hidden when `pickerRecent` empty
- Green on recent chips = content_hash only (223)

## Amend

**[232](232-pdf-import-remove-recent-strip.md)** removes the strip from `PdfImportScreen` (0.3.230). Label rule above is historical for 0.3.226–0.3.229.

## Version

**0.3.226** (screen strip removed in **0.3.230**)
