# 209 — Practice cycle wide evidence (**KILLED**)

Version: **0.3.211** · **Status: killed**

## Decision

Product owner: this pipeline is not needed. No local collection, no deferred
flush, no cloud ingest capacity for practice-cycle evidence.

## What was removed / hard-off

- Kill is **permanent**: `practice_cycle_evidence_enabled()` always `False`
  (env cannot re-enable).
- Status flags `practice_cycle_evidence` / `mobile_practice_cycle_evidence` stay `false`.
- Mobile status parse hard-forces `mobilePracticeCycleEvidence = false`.
- Kinds `practice_cycle_wide` / `practice_evidence_flush` **removed** from
  evidence allowlists — ingest drops them (no JSONL growth from old clients).
- Practice screen no longer probes / appends / flushes.
- Local queue `append` is no-op; `clearAll` wipes leftover device files.
- Uploader only clears local leftovers (never POSTs batches).

## Still intact (not this chip)

- design/208 process grooming (rate nudge) — separate
- design/176 focus session evidence kinds
- Agent evidence bus for papers / ingest / shadowing gate (169…)

## Non-goals of the kill

Deleting historical JSONL already in GCS (ops one-shot if desired).
Removing dead `mobile/lib/practice_evidence/*` source files (kept as no-ops).
