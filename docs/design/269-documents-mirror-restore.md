# 269 — Documents mirror empty-gate restore

Version: **0.3.265** · Status: **locked**  
Depends [268](268-documents-mirror-write.md) · Parent [262](262-documents-mirror.md)

## Locked

1. After login: if MES granted and **disk index + session dirs truly empty** (soft-hide UI empty ≠ empty), restore from `Documents/문장읽기/{uid}` **without confirm**.
2. Wrong uid / partial fail → banner + abort (no half-success claim).
3. Never restore soft-delete prefs, SAF grants, session tokens, voice.

## Kill

Revert restore call site.
