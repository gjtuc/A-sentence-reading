# 394 — The prompt follows the line being read

**Version:** 0.3.433 · Status: **locked**

## Why

The prompt scrolled by time: `offset = maxExtent × pos / (0.85 × duration)`.
Nothing moved until the player reported the clip length, and then the offset
jumped ahead to catch up. The user saw a fast scroll that started late, often
after the voice was already past the visible lines.

## Locked

1. In listen and speak, when the sentence has word spans, the prompt follows the
   lit word (the follow light). The lit word carries a key (`WordPhoneText.litKey`).
   When its line top changes, `Scrollable.ensureVisible` glides that line to
   `kFollowLineAlign` (0.3, upper third) over `kFollowLineGlide` (320 ms).
   Inside one line nothing moves.
2. A finger drag on the prompt (`UserScrollNotification` with a direction) holds
   it for the rest of that phase. The next phase starts at the top and follows
   again. The app's own glides do not count as a finger.
3. Without spans, and in my-take replay, the old time walk stays. It also obeys
   the finger hold.
4. If no duration event has come by the first position tick, the player is asked
   once (`getDuration`).
5. The first duration is logged as cycle step `follow_clock` with `dur_wait_ms`,
   `dur_source` (`event` or `asked`) and `dur_ms`. This checks the late-start cause.

## Tests

`mobile/test/follow_line_scroll_test.dart`.
