# 268 — Documents mirror write triggers

Version: **0.3.265** · Status: **locked**  
Depends [264](264-documents-mirror-mes-channel.md) · Parent [262](262-documents-mirror.md)

## Locked

1. After successful paper handoff / local session write: mirror paper folder essentials (session, manifest, figures, source when present).
2. Mirror bookmarks/annotations/notes JSON when changed (187); **never** voice.
3. Fail → banner / evidence; never claim success.
4. In-app SoT remains primary.

## Kill

Disable mirror writes via client flag later; revert hooks.
