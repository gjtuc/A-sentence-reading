# 209 — Practice cycle wide evidence (deferred flush)

Version: **0.3.210**

## Intent

During focus practice, collect **dense numeric process evidence** per chunk cycle
(wide event) so later grooming triggers can be chosen from real data.

- **Not** voice blobs or paper text
- **Not** user-visible scores/tips
- Upload **after** focus ends (local durable queue during session)

## Locked

- Kind: `practice_cycle_wide` (one wide event per cycle attempt)
- Flush summary: `practice_evidence_flush`
- Details: int / bool / double / snake tokens only (`_safeDetails` contract)
- `schema_v: 1`
- Durable JSONL queue under app support dir (not EvidenceBus ring-200)
- Focus active: **no** network ingest for these events
- Flush on: give-up, app pause while on practice screen, screen dispose
- Kill: `ASR_PRACTICE_CYCLE_EVIDENCE=0` → status false; missing key → **on**
- Separate from design/208 grooming kill

## Non-goals

PCM correlation / waveform features (Later — schema leaves `feat_ok` for extension).
Actuator changes. UI scores.
