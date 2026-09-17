# 313 — Follow light and launch destination

Locked. Display text stays the paper. Spoken audio is unchanged (`speak_norm` stays v6 unless the spoken string changes).

## Follow light

During listen and speak, light the printed word that the current audio slice belongs to.

- `POST /api/tts/spoken` also returns `spans`: `{start, end, weight}` into the display string. `weight` is the spoken-slice length. Dropped parentheses have weight 0.
- The phone does not reimplement speak rules. No spans, or a failed alignment, means no light.
- One printed token covers its whole spoken slice (`CVD` stays lit for `c v d`).
- Clock is the player media position, not wall time, and is not divided by playback rate.
- Replay keeps the red miss blink only. Follow light is off there.
- A late position from the previous chunk must not light the next chunk.

## Launch destination

Setting, uid-scoped, default `library`. Changing it does not navigate. Next process start only, once, after login and the library list.

| Value | Open | Missing paper |
|---|---|---|
| `library` | Library | — |
| `read` | Latest reading progress `at` | Library |
| `practice` | Latest practice progress `at`, then practice | Library |

Do not use `lastPracticePressedAt` or `last_read_left_at` as the recency key. Practice launch opens the paper session first. Shadowing off or the 90-day auto-off falls back to library. A notification open wins. Resume from background does not run this again.
