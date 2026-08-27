# design/148 — Mobile References panel

**Version:** 0.3.69  
**Scope:** cite panel only (no Azure figure+caption composite in this release).

## UX

Layout in sentence panel (split mode):

1. Sentence text (cite markers stripped for display)
2. Fig ref chips
3. **References panel** (scrollable, max ~22% screen height)
4. Split bar
5. Figure panel

### Open reference

- Tap a bibliography row → `POST /api/cite/resolve` → external browser (`url_launcher`).
- Resolution order matches web design/41: DOI in text → publisher URL; else Crossref; else Google Scholar.

### Settings

- **참고문헌 패널 표시** — device pref, default **ON**, scoped by uid (`asr.cite_panel.v1.$uid`).
- When OFF: panel hidden only; `[1,2]` markers **still stripped** in sentence display (design/49).

### Server kill

- `/api/status` → `mobile_cite_ref_panel: true` (default).
- Kill: `ASR_MOBILE_CITE_REF_PANEL=0` → panel hidden + settings toggle disabled.

## Invariants (design/41)

- Cite tap / resolve **never** changes `sentenceIndex` or `figureIndex`.
- Raw sentence `text` kept for parsing; display uses `stripCiteMarkersForDisplay`.

## Mobile implementation

| Piece | Path |
|-------|------|
| Cite parse/strip | `mobile/lib/api/cite_refs.dart` |
| Session `references` | `mobile/lib/api/reading_models.dart` |
| Resolve client | `mobile/lib/api/client.dart` → `resolveCite()` |
| Prefs | `mobile/lib/api/cite_panel_store.dart`, `cite_panel_controller.dart` |
| Reader UI | `mobile/lib/screens/reader_screen.dart` → `_CiteRefPanel` |
| Settings | `mobile/lib/screens/settings_screen.dart` |

## Data

- Server ingest already populates `session.references` (`extract_bibliography`).
- Re-open cached paper — no re-upload required if bibliography was extracted at ingest.

## Out of scope (phase 2)

- Azure figure+caption composite PNG
- Hide figure panel caption `Text`
- Azure caption body-verb filter (`shows`, etc.)
- `text_ko` cite strip
