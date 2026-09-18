# 318 — Shared JSONL store for observability buses

**Version:** 0.3.314 · Status: **locked** (ops; no product bump)  
Amends [169](169-agent-evidence-bus.md) · [168](168-ingest-observability.md) · [169g](169g-causal-handoff-evidence.md)

## Why

`evidence_bus`, `ops_events`, `error_logs`, and `upload_audit_log` each copied
JSONL parse / retain / trim / GCS pull+push. A fix in one store did not
reach the others. Schemas and kill switches stayed different on purpose;
only the file body was duplicated.

## Locked

1. Shared implementation lives in `llm/jsonl_store.py`.
2. Buses keep their public functions (`filter_retained`, `append_*`,
   `rotate_events`, `local_events_path`). Tests may still patch those names.
3. Kinds, floors, and kill switches do not move. Shrinking `FROZEN_KINDS`
   is still forbidden.
4. Missing/bad `ts` is kept (observability fail-closed).
5. No product version bump.

## Not this chip

- Merging the three event schemas
- Admin/user evidence UI
- Day-sharded GCS objects
