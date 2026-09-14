# 271 — Find-watch vs pick race

Version: **0.3.264** · Status: **locked**  
Amends [242](242-pdf-import-find-watch.md) · [238](238-pdf-import-open-document-pick.md)

## Locked

1. Disarm find-watch **before** opening `pickDocuments` / Downloads pick UI (not only inside `_importPickedDocs`).
2. Pause find-watch rescan timer while the system picker is open.
3. Confirm dialog must no-op safely if hit URI was cleared.
4. Empty pick cancel may leave watch armed until timeout (242) — OK.

## Kill

Revert.
