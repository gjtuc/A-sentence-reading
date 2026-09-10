# 216 — Cite display / TTS / practice strip consistency

Version: **0.3.216** · Status: **locked**

받침: [41](41-cite-ref-open.md) · [49](49-cite-display-clean.md) · [182](182-ai-ask-partial-highlight.md) · [205](205-tts-spoken-form.md) · [212](212-practice-skill-adapt.md)

## Intent

Keep citation markers in **stored** sentence/chunk text (chips · bibliography).
Use **one strip SoT** for eye, ear, and practice display/score inputs — no
one-off replaces.

## Locked (J1–J12)

1. **J1** Store/plan/GCS `text` & chunks keep cites.
2. **J2** SoT = `strip_cite_markers_for_display` (Py ≡ Dart ≡ JS).
3. **J3** Cite chips/parse always use **raw**.
4. **J4** TTS: strip numeric `<sup>n</sup>` **before** HTML→spoken; keep
   `cm<sup>−1</sup>`-style unit supers.
5. **J5** design/205 pipeline order amended: strip cites → HTML sub/sup spoken.
6. **J6** Practice plan/density = **raw**; UI Text only strips.
7. **J7** Practice spoken/score key = **same display string** as UI (strip once
   client-side; server strip idempotent).
8. **J8** Translate v1 = **display-only** strip (no strip-before-translate).
9. **J9** `speak_norm_version` **v3** (cache bust).
10. **J10** 182 plain = `annotationPlainForSentence` (strip → plainFromRichHtml).
11. **J11** Plain-trailing guards: do **not** strip `Fig./Table/…` labels or
    year tokens (1900–2099); still strip ACS `.1−5` / `.6−9`.
12. **J12** Non-goals: author-year parser, References TTS, mid-sentence ACS
    plain expansion, Dart `tts_speak` port.

## Files (primary)

| Path | Change |
|------|--------|
| `cite_refs.py` / `.dart` / `cite_refs.js` | Fig/year guards on plain trailing (+ parse) |
| `tts_speak.py` | strip before `_ToSpoken` |
| `tts_speak_policy.py` | default `v3` |
| `shadowing_practice_screen.dart` | display + spoken/score strip |
| `docs/design/205-…` | pipeline amend |

## Tests

- `tests/test_cite_display_clean.py` — Fig/year + ACS regressions
- `tests/test_tts_speak.py` / `205` — `<sup>12</sup>` not spoken; units kept; v3
- practice: UI/spoken use stripped chunk

## Version

**0.3.216**
