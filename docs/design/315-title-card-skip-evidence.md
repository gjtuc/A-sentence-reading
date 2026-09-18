# 315 — Title card skip evidence (counts, not a product fix)

**Version:** 0.3.312 · **Status:** locked · **Parent:** [297](297-session-title-from-info-or-head.md) · [169g](169g-causal-handoff-evidence.md)

## Why

A phone capture showed the first sentence card holding front matter chrome
(authors, `A R T I C L E I N F O`, `Keywords:`) while the header carried the
correct title. `align_title_sentences` exists to replace exactly that card, so
the question was why it had not fired.

Reading the code, alignment is skipped on two paths — and **both reported a
token that hid the skip**:

| Path | Old token | Problem |
|---|---|---|
| `title_usable(picked)` false (publisher file id such as `1-s2.0-S…-mmc1`) | `kept` | claims the card already equalled the title; chrome survives unseen |
| `doc_role == "supplementary"` | `absent` | indistinguishable from "no title card at all" |

Live `title_pick_done` for the week held only `kept` and `replaced`, so the
skip paths could not be counted at all. The capture itself predated the 0.3.310
title work (`633d076`, `7286744`, `f38360e`), so whether a skip still happens on
real papers is **unknown** — which is the point of this chip.

## Product (locked)

**No behaviour change.** The chrome card still stands when alignment is skipped.
Replacing or dropping it is the next chip, written from what this evidence says.

## Implementation rules

| # | Rule |
|---|---|
| R1 | `align_title_sentences` returns `skipped_unusable` when `title_usable(picked)` is false **and** a `title` section exists. No title section stays `absent`. |
| R2 | `api/app.py` sets `skipped_si` before the `doc_role == "supplementary"` early return. |
| R3 | Dart `titleCardToken` mirrors R1 so client and server agree. |
| R4 | Token vocabulary is **add-only**: `absent` · `kept` · `replaced` · `skipped_unusable` · `skipped_si`. |
| R5 | No paper text in evidence. The token and `char_n` only. |

## Non-goals

- Changing which title is picked (that is 297 / 310)
- Dropping or rewriting the chrome card (next chip)
- A new evidence kind — `title_pick_done` already carries `title_card`

## Acceptance

- `scripts/pytest.cmd tests/test_session_title_pick.py`
- `scripts/flutter_test.cmd test/title_card_skip_test.dart`
- After deploy: `python scripts/pull_evidence.py --kind title_pick_done --since 7d`
  and count `skipped_unusable` / `skipped_si`. A nonzero count names the paper
  class the next chip must handle.

## Version bump

`app.py` · `mobile/pubspec.yaml` · `mobile/lib/config.dart` → `0.3.312`
