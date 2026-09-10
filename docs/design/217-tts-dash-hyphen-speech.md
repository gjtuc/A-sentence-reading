# 217 — TTS dash/hyphen speech (minus ≠ link)

Version: **0.3.217** · Status: **locked** · Extends [205](205-tts-spoken-form.md) · [90](90-tts-unit-lexicon.md) · [212](212-practice-skill-adapt.md)

## Intent

Stop Neural2 from saying **“minus”** for alloy/abbrev hyphens (`Ni-Cu`, `F-T`)
so practice ear-form matches conversational English. Keep true minus for
negatives, charges, and unit inverses (as *per …*, not “minus”).

## Locked (J1–J10)

1. **J1** SoT = server `spoken_text_for_tts` only (no Dart port).
2. **J2** Display / plan / chunks stay raw.
3. **J3** Linking hyphen/en-dash → silence (space).
4. **J4** Spoken “minus” only for U+2212 leftovers, unary `-`/`−`+digit, charges/sup path.
5. **J5** Single-letter pairs `F-T` / `I-V` → letter-speak (`f t`, `i v`) before elements.
6. **J6** Multi-letter element chains `Ni-Cu` → space → existing element expand.
7. **J7** Digit–digit → `to` only under narrow rules (pH / wt% / both ≥2 digits); never `10-3` decade OCR as range; never `Ni-Cu` as `to`.
8. **J8** `speak_norm_version` **v4** (cache bust).
9. **J9** No SSML / LLM rewrite.
10. **J10** `6061-T6` → dash silence (`6061 T six` path).

## Pipeline (amends 205)

… collapse → **dash A** → **units** → symbols → acronyms → **dash B** → elements → **dash C** → prosody …

| Pass | When | Does |
|------|------|------|
| A | pre-units | unary protect; `X-Y` / compound link → space; narrow range → `to` |
| B | pre-elements | `([A-Z]) ([A-Z])` → `a b` letter-speak |
| C | post-elements | scrub leftover ` - ` / link dashes; restore unary → ` minus ` |

**Units before symbols** so `cm−1` is not broken by `−` → ` minus `.

## Non-goals

Whole-sentence paraphrase; stripping hyphens on screen; saying “dash” for alloys.

## Tests

`tests/test_tts_speak_dash.py` — Ni-Cu, F-T, units, unary, I-V, ranges, idempotent, v4.

## Version

**0.3.217**
