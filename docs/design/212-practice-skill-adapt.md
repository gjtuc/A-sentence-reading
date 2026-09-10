# 212 — Practice skill adapt (STT accuracy · chunk density · TTS tiers)

Version: **0.3.212** · Status: **locked**

받침: [80](80-shadowing-chunks.md) · [82](82-shadowing-practice-loop.md) · [103](103-mobile-tts-voice-random.md) · [176](176-focus-practice-pomodoro.md) · [205](205-tts-spoken-form.md) · [206](206-practice-speak-tts-volume.md) · [208](208-practice-process-grooming.md) · [209](209-practice-cycle-wide-evidence.md)

## Intent

On-device practice measures **how much of the TTS spoken-form content words**
the learner produced (order-insensitive), shows block/day **인식 일치도** on the
focus calendar, and softly adapts:

1. **Chunk density** (growing step count) — fine difficulty inside a TTS tier  
2. **TTS skill tier** (6 bands) — only when density hits a soft bound  

## Locked product

1. **Reference = ear form:** `spoken_text_for_tts(chunk_display)` + same
   `speak_norm_version`. Never score against on-screen paper glyphs alone.
2. **API SoT:** `POST /api/tts/spoken` → `{spoken, speak_norm_version}`.
   Do **not** change `/api/tts` MP3 body. Do **not** port `tts_speak` to Dart.
3. **Metric:** content-word **multiset coverage** (insertions do not hurt):
   `accuracy = covered(ref, hyp) / |ref|`. Empty content-word ref → unscored.
4. **37/38 carve-out:** Reader「말하기」stays **no score**. Practice skill % is
   this chip only.
5. **STT timing:** after mic stop on the take file (or cloud recognize of that
   file). **No mid-speak** SpeechRecognizer (cannot share mic with MediaRecorder).
6. **STT engine v1 (interim):** `POST /api/stt/recognize` on the take bytes
   (Gemini). Transcript used **only in memory** to score, then discarded —
   not stored in evidence / not a 209-style JSONL pipeline.
   Kill: `ASR_PRACTICE_STT_CLOUD=0`. On-device file ASR = Later.
7. **Samples / % / density / tier:** device-local prefs. No transcript/audio in
   169 evidence (P5). Optional evidence: bins/enums only.
8. **Density:** `effectiveChunks(basePlan, density)` merge/insert prefixes —
   **no Gemini rebuild**. Soft min/max relative to sentence length.
9. **Adapt (block mean, scoredN ≥ 5):**
   - ≤60% → density +1 (finer)
   - ≥75% → density −1 (coarser)
   - soft-max + still low → TTS tier −1
   - soft-min + still high → TTS tier +1
   - one axis per event; hysteresis/cooldown
10. **TTS UI:** `fixed` | `random_auto`. Six internal tiers (0..5). Insufficient
    samples → tier **2 (보통)**. Migrate old random_* → auto + mapped tier.
11. **Calendar:** show 인식 일치도 orthogonal to 176 block heat. Small n → `—`.
12. **Grooming 208:** independent; rate order = tier band × groom scale × clamp.
13. **Kill:** `ASR_PRACTICE_SKILL=0` → status false (missing → on).

## Non-goals (this ship)

- Mid-speak live STT · Vosk/sherpa on-device file engine  
- Reviving design/209 practice_cycle_wide upload  
- Putting `accuracy` on `/api/stt/compare`  
- Replacing on-screen chunk text with spoken form (205)

## Files (primary)

| Path | Role |
|------|------|
| `src/.../tts_speak.py` | SoT spoken |
| `src/.../practice_skill.py` | kill flags |
| `app.py` | `/api/tts/spoken` · status |
| `mobile/lib/practice_skill/*` | score · store · density · adapt · stt |
| `tts_models.dart` | tiers · `random_auto` |
| `shadowing_practice_screen.dart` | wire |
| `focus_practice_calendar_sheet.dart` | % |

## Version

**0.3.212**
