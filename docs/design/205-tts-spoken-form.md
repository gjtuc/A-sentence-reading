# 205 — TTS spoken form (display ≠ ear)

Version: **0.3.205** · Extends design/15 · 88 · 90

## Locked policy (`SpeakPolicy` v2)

| Field | Value | Why |
|-------|--------|-----|
| `chem_style` | `symbol_digits` | MathCAT-like (“H two O”); common-name (methane) later via lexicon flag |
| `acronym_mode` | `lexicon` | Known initialisms → letters or expand; miss → leave |
| `full_name_abbrev` | `prefer_one` | Drop redundant `(NMR)` / `NMR (...)` pair |
| `pause_mode` | `punctuation` | Neural2: rewrite text, not SSML (SSML later, flag off) |
| `speak_norm_version` | `v2` | Included in TTS cache key (GCS bust on rule change) |
| `locale` | `en-US` | Matches default Neural2 |

## Non-goals (this ship)

- Whole-sentence colloquial paraphrase / fillers
- Replacing on-screen text with spoken form
- Full SSML / SRE MathML (needs structured math)
- Per-request LLM rewrite

## Pipeline stages (order locked)

1. unescape HTML  
2. HTML sub/sup → spoken  
3. strip cites  
4. strip literal tags  
5. unicode sub/sup  
6. **chem aliases** (exact graphemes, optional)  
7. plain chem digits (conservative)  
8. strip section prefix  
9. **collapse full-name + abbrev**  
10. symbols  
11. units (before elements)  
12. **acronym lexicon** (before elements — NMR ≠ nitrogen)  
13. elements (bare-skip preserved)  
14. **light prosody** (arrow commas)  
15. whitespace collapse  

## Cache

`cache_key = sha24(f"{speak_norm_version}|{voice}|1.00|{spoken}")`

Bump `speak_norm_version` when rules change without changing spoken string shape (or when intentional bust needed).

## API

`POST /api/tts` unchanged. Server-only normalize. Optional status field `tts_speak_norm`.

## Tests

- `tests/test_tts_speak.py` — collisions + new acronym/collapse  
- Cache key includes `v2`  
- Idempotent: `f(f(x)) == f(x)`

## Rollback

`ASR_TTS_SPEAK_NORM=v1` forces legacy cache namespace + minimal path if needed; code keeps single pipeline with version in key.
