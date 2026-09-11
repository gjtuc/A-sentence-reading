# 239 — PDF import advisory set row (main+SI)

Version: **0.3.234** · Status: **locked**  
Depends [218](218-supplementary-soft-pairing.md) · [228](228-pdf-folder-advisory-preview.md) · [221](221-upload-reservation-queue.md)

## Locked

- Dart `normalizePairingKey` = Python `normalize_pairing_key` twin.
- Visible list: exactly one main + one SI sharing key → **one set row**; checkbox selects both URIs.
- Enqueue atomic: need ≥2 free slots; abort both if either read fails before reserve.
- Upload `displayName` = SAF name (228). Advisory never gates singles.

## Non-goals

N:1 silent pairing · auto-merge.

## Version

**0.3.234**
