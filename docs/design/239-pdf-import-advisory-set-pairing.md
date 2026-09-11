# 239 — PDF import advisory set row (main+SI)

Version: **0.3.235** · Status: **locked**  
Depends [218](218-supplementary-soft-pairing.md) · [228](228-pdf-folder-advisory-preview.md) · [221](221-upload-reservation-queue.md) · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- Dart `normalizePairingKey` = Python `normalize_pairing_key` twin.
- `pairingKey` on `ScannedPdfEntry`: prefer `entry.pairingKey` when non-empty; else `normalizePairingKey(advisoryTitle)`.
- NFKC: Android `Normalizer.NFKC` via channel when available; Dart `_nfkc` common-fold fallback kept in sync.
- Optional advisory cache **v=7** field `pairing_key` (wipe on schema bump).
- Visible list: exactly one main + one SI sharing key → **one set row**; checkbox selects both URIs.
- Enqueue atomic: need ≥2 free slots; abort both if either read fails before reserve.
- Upload `displayName` = SAF name (228). Advisory never gates singles.

## Non-goals

N:1 silent pairing · auto-merge.

## Version

**0.3.235**
