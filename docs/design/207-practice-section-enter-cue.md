# 207 — Practice section-enter cue (immersive)

Version: **0.3.207**

## Locked

While focus session is active (chrome hidden), show a **one-shot floating SnackBar**
with the new section display name only when the practice loop **enters a different section**.

- Same-section next chunk / next sentence: no cue
- Listen chrome visible (not focusing): no cue (header already shows section)
- Manual sentence picker while focusing: cue if section changed

Duration ~1.8s. No persistent badge.
