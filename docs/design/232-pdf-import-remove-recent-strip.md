# 232 — Remove 「최근」 strip from PDF import screen

Version: **0.3.230** · Status: **locked**  
Amends [227](227-pdf-import-recent-label.md) · [226](226-pdf-folder-import-browser.md)

## Problem

Folder import already lists all PDFs; the bottom 「최근」 strip duplicated noise and cluttered the screen.

## Locked

| Include | Exclude |
|---------|---------|
| Remove `_RecentStrip` UI from `PdfImportScreen` | Deleting prefs recent store / remember APIs |
| Drop design/227 on-screen label requirement for this screen | Changing upload picker sheet 「최근」 (223) |

## INVARIANT

- `pickerRecent` may still be written for other surfaces; import screen simply does not render it.
- Green border / advisory behavior unchanged.

## Version

**0.3.230**
