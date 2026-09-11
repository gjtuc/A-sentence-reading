# 243 — PDF import remaining polish (0.3.235)

Version: **0.3.235** · Status: **locked**  
Amends [237](237-pdf-import-doi-find-cta.md)–[242](242-pdf-import-find-watch.md) · [226](226-pdf-folder-import-browser.md)

## Summary

Post-0.3.234 polish ship. Product contracts live in amended 237–242; this note indexes the locked deltas:

| Area | Lock |
|------|------|
| 237 find CTA | Hide when set row or mate already present (same pairing key, opposite role, ready) |
| 238 pick | Partial multi-pick → enqueue failed copies only; `mode=copy_partial` |
| 239 pairing | Prefer `entry.pairingKey`; NFKC Android Normalizer + Dart fallback; cache v7 `pairing_key` |
| 240 library | Disk keeps `pairedCacheId`+`canMerge`; `pairAdjacent`; visual connector; **no auto-merge** |
| 241 write | Proactive writable probe on grant load; READ-only banner |
| 242 watch | Pick disarms; ignore copied URIs; bump baseline; confirm=select only; no MES |

## Version

**0.3.235**
