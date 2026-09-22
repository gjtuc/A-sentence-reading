# 320 — Practice rest-cover watchdog

**Version:** 0.3.315 · Status: **locked**  
Amends [274](274-practice-blank-rest-soft-entry.md) · [314](314-practice-miss-review.md)

## Why

After a successful replay the black rest cover can stay up past the scheduled
rest: a one-shot `Future.delayed`, miss-review TTS that paints the word only
after bytes return, or an abort that leaves `RhythmPhase.rest`. Focus time
can still be left and the next prefix chunk can already exist. The stall is
rare and did not reproduce on retry.

## Locked

1. The rest cover has a wall-clock cap:
   `restCoverWatchdogLimit(scheduledRest, reviewWordN)`.
   No review: scheduled rest + 2s (or 2s if rest is zero).
   With review: one attempt budget (12s play + mic ready + 12s speak cap + 2s pad + 8s STT) × 5 tries × wordN, plus the 314 tail + 2s.
2. Past that cap, emit `shadowing_loop_event` `code=rest_overrun`, bump the
   cycle token, drop the cover, and start the next listen. Do not add a
   frozen kind.
3. Paint the review word before `synthesizeTts`. A hung first-word fetch
   must not look like extra blank rest.
4. Rest and review-tail waits poll every 400ms. Pause, give-up, background,
   or a new cycle token drop the cover. They do not start the next listen.
5. Give-up, sentence jump, and dispose cancel the watchdog.

## Not this chip

- Changing rest length `15s × k / N`
- Repeating the finished chunk
- Auto figure grounding / summary / RSVP
- Shipping the APK in this chip
