# 267 — Fine difficulty × in-tier rate bias

Version: **0.3.266** · Status: **locked**  
Amends [212](212-practice-skill-adapt.md) §12 rate order · [103](103-mobile-tts-voice-random.md) · [208](208-practice-process-grooming.md) · [274](274-practice-blank-rest-soft-entry.md)

## Problem

Fine difficulty (chunk density) only changes step count. Within a TTS skill tier, rate was uniform-random, so density did not fine-tune speed exposure.

## Locked product

1. **Tier bands + locale/intonation weights unchanged.**
2. **Density sign unchanged:** `density↑` = more chunks = easier; `density↓` = fewer chunks = harder (212/244).
3. **Within-tier rate prior:** `density↑` → more mass toward slower end of band; `density↓` → more mass toward faster end. Still random (not a fixed rate).
4. **Sample order:** tier band → density skew → × grooming (208) → clamp 0.5–2.2.
5. **Practice TTS only** (`shadowing_practice_screen` chunk play). Reader / `fixed` mode: no bias.
6. Weak skew: `γ = clamp(1 + 0.35·d, **0.40**, 1.8)` (274 gmin; was 0.45). Do not change 215 epoch thresholds here.

### User wording map

| User | Code density | Chunks | Rate prior |
|------|--------------|--------|------------|
| Fine difficulty low | + (finer) | more | slower bias |
| Fine difficulty high | − (coarser) | fewer | faster bias |

## Non-goals

Locale/voice weight changes · tier endpoint changes · invert density · Gemini rebuild · Reader TTS bias.

## Kill

`ASR_PRACTICE_RATE_BIAS=0` (default on) · also off when `ASR_PRACTICE_SKILL=0` · revert.

## Tests

Mean rate at density=+2 < mean at density=−2 (same tier, many draws); all samples inside band.
