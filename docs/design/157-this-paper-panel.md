# 157 — Title section "이 논문" panel

**Version:** 0.3.86  
**Scope:** mobile Title 1/N row + server `document_citation` ingest field.

## UX

Title 섹션 **첫 문장(1/N)** 에서만:

1. Sentence text (cite markers stripped)
2. **이 논문** panel — single bibliographic row
3. Fig ref chips
4. References panel (when `[n]` cites match)

Tap row → `https://doi.org/{doi}` when DOI known; else `POST /api/cite/resolve` (design/41).

### Settings

- No separate toggle — follows **참고문헌 패널 표시** (`CitePanelController`, default ON).
- Copy mentions Title "이 논문" link is included.

### Server kill

- `/api/status` → `mobile_this_paper_panel: true` (default).
- Kill: `ASR_MOBILE_THIS_PAPER_PANEL=0`.
- When `ASR_MOBILE_CITE_REF_PANEL=0`, this panel is also hidden.

## Data

Ingest populates `session.document_citation`:

```json
{
  "text": "Paper title or bibliographic line",
  "doi": "10.1021/…",
  "source": "front_matter",
  "confidence": "high"
}
```

Extraction (`document_citation.py`): front matter DOI → title-section DOI → title-only → `{}`.

Cached papers without the field: mobile `effectiveCitation()` falls back to title-section DOI regex or `session.title`.

## Invariants (design/41)

- Tap / resolve never changes `sentenceIndex` or `figureIndex`.
- TTS does not read the panel row.

## Implementation

| Piece | Path |
|-------|------|
| Extract | `src/sentence_reading/document_citation.py` |
| Session field | `src/sentence_reading/models.py` |
| Ingest | `src/sentence_reading/api/app.py` |
| Mobile model | `mobile/lib/api/document_citation.dart` |
| Reader UI | `mobile/lib/screens/reader_screen.dart` → `_ThisPaperPanel` |
