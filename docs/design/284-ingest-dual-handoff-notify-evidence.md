# 284 — Ingest dual-run · handoff · notify evidence densify (overkill)

Version: **0.3.279** · Status: **locked**  
Amends [169](169-agent-evidence-bus.md) · [169g](169g-causal-handoff-evidence.md) · [169m](169m-lease-sweeper-obs.md) · [175](175-papers-gcs-orphan-invariant.md) · [185](185-local-paper-sot.md) · [74](74-bg-upload-notify.md) · [282](282-merge-reader-honesty-evidence.md)  
Incident: 2026-09-15 · job `job_90a5449c8f5c` · cache `45efe205811d`→`18ed9907bba5` · APK **0.3.268** · phone notify miss UI

## Why (live JSONL gaps — not product fix yet)

Agents could reconstruct the story only by **cross-reading** many kinds + source code. JSONL alone could **not** answer in one pull:

| Question | Had | Missing |
|----------|-----|---------|
| Two workers on one job? | `lease_heartbeat` tok8 alternation (sampled 1/4) | No `ok:false` dual-lease kind; no detector |
| Who GC’d handoff target? | `papers_supersede_gc` on loser id | **`winner_id` stripped by `_safe_details`** (digit-leading cache ids fail `^[a-z]…`) |
| Handoff fail vs queue success? | separate `paper_handoff_done ok=false` + `upload_queue_pump_done ok=true` | No single gate event; **handoff return ignored in product** (fix later) |
| Notify miss? | UI string only | **`paper_notify_open` not on device 0.3.268** (kind exists in repo ≥282 / floor) |
| Join job ↔ handoff ↔ supersede? | mobile `trace_id` on some rows | **server handoff/supersede often `job_id=null` `trace_id=null` `content_hash=null`** |
| Poll id vs index winner? | poll terminal `has_cache_id` | No `poll_cache_id` vs later index id mismatch kind |

**Hard rule for this chip:** observability + allowlist/floor only. **No** lease algorithm change, **no** handoff/notify product gate, **no** supersede policy change.

---

## Hard constraints

1. No title / path / filename / DOI / paper text / emails / tokens in `details` or `message` beyond existing redact.
2. Opaque ids: top-level `cache_id` / `job_id` / `trace_id` / `content_hash` use existing `_safe_*` (hex/alnum OK including digit-leading).
3. **`details` string values that are cache ids MUST use prefixed form** `c{cache_id}` (leading `c`) so `_safe_details` keeps them — **or** put partner id only in top-level fields (`cache_id`=loser, new optional top-level later). Preferred: `winner_id` → `c`+id in details **and** mirror winner as top-level via second emit if needed.
4. Allowlist **py + dart** twin; add-only `FROZEN_KINDS` + `FROZEN_EMIT_MARKERS`.
5. Fail-closed: missing join keys on new kinds = emit anyway with `join_incomplete=1`.

---

## Locked emit map

### P0 — Fix silent drop (infra)

| # | Change | Where |
|---|--------|--------|
| P0a | When emitting `papers_supersede_gc`, set `details.winner_id` = `c` + winner hex (always letter-prefix). Keep `cache_id` top-level = **loser**. | `papers_gcs.gc_superseded_paper` |
| P0b | Unit test: digit-leading winner survives `_safe_details` only when prefixed; unprefixed dropped (documents current bug). | `tests/test_evidence_safe_details_cache_id.py` (new) |
| P0c | Stamp `job_id` + `content_hash` + `trace_id` on server `paper_handoff_*` and `papers_supersede_gc` when caller has them (thread job context / optional args). | `paper_handoff.py`, `papers_gcs.py`, ingest save→upload path |

### E1 — `ingest_lease_dual` (new · error · no sample)

**When:** on each `lease_heartbeat` emit path (or reclaim claim): if GCS/mem already shows a **different** `lease_tok8` for same `job_id` while `_local_running` or age still valid → also emit dual.

| Field | Type | Meaning |
|-------|------|---------|
| `mem_tok8` | str | this instance |
| `other_tok8` | str | conflicting token (from GCS snapshot) |
| `cr_rev8` | str | this instance |
| `hb_seq` | int | |
| `dual` | 0/1 | always 1 on this kind |

`ok=false`, `severity=error`, `code=lease_dual`.

**Minimum:** compare `mem_tok8` vs `gcs_tok8` when both non-empty and unequal on heartbeat/reclaim.

### E2 — `ingest_cache_id_fork` (new · consistency)

**When:** `save_paper_session` / `figure_meta_write` activity `ingest_store` completes and job already has `target_cache_id` or prior artifact cache_id for same `content_hash` **≠** new id.

| Field | Meaning |
|-------|---------|
| `prior_cid` | `c`+prior |
| `new_cid` | `c`+new (also top-level `cache_id`=new) |
| `same_hash` | 1 if content_hash matches job |
| `activity` | `ingest_store`\|`reanalyze`\|… |

`ok=false`, `code=cache_id_fork`.

### E3 — densify `paper_handoff_done` (mobile + server)

Every done/fail path:

| Field | Meaning |
|-------|---------|
| `handoff_ok` | 0/1 |
| `files_ok_n` | files written this attempt |
| `files_want_n` | manifest file count (0 if unknown) |
| `has_session` | 0/1 after attempt |
| `ack_ok` | 0/1 |
| `wiped` | 0/1 (server ACK path) |
| `fail_code` | `sha_mismatch`\|`http_404`\|`empty`\|`exception`\|`ok` (snake) |

Mobile fail today often has **empty details** + message only → must fill ints.

Join: pass `job_id` from active ingest into `_runPaperHandoff` record calls.

### E4 — `notify_complete_gate` (new · mobile · boundary)

**When:** immediately before `showCompleted` / `showFailed` after upload/reanalyze handoff+confirm (both success and fail paths).

| Field | Meaning |
|-------|---------|
| `handoff_ok` | 0/1 (return of `_runPaperHandoff`) |
| `confirm_ok` | 0/1 |
| `confirm_via` | `list`\|`disk`\|`none` |
| `will_notify` | `completed`\|`failed`\|`none` |
| `poll_cache_id` | `c`+id from poll |
| `list_has_poll_id` | 0/1 |
| `disk_has_poll_id` | 0/1 |

`ok` = (`will_notify==completed` **and** `handoff_ok==1` **and** `confirm_ok==1`).  
If completed notify with `handoff_ok==0` → `ok=false`, `code=notify_without_handoff` (sensor only; still call showCompleted until product chip).

### E5 — densify `paper_notify_open` (ship on device)

Already in allowlist/floor (282). Ensure:

| Field | Meaning |
|-------|---------|
| `after_refresh` | 0/1 |
| `list_n` | papers.length |
| `miss_reason` | `empty_id`\|`not_in_list`\|`collapsed_mate`\|`soft_hidden`\|`unknown` |
| `mate_resolve` | 0/1 if opened via pairedCacheId (**product later**; this chip only **detect** if id matches any `pairedCacheId` while miss on id → `miss_reason=collapsed_mate`) |

Require APK ≥ chip version (not 0.3.268).

### E6 — densify `upload_queue_pump_done`

Add: `handoff_ok`, `confirm_ok`, `notify_gate_ok` (0/1/-1), `job_id` top-level when known.

### E7 — `poll_cache_vs_index` (new · server or mobile after refresh)

**When:** after ingest terminal ok + library refresh: poll/result `cache_id` ∉ index ids but another id shares same `content_hash` → emit.

| Field | Meaning |
|-------|---------|
| `poll_cid` | `c`+ |
| `index_hit` | 0/1 |
| `alt_cid` | `c`+ first same-hash index id if any |
| `same_hash` | 0/1 |

`ok=false` when `index_hit==0` and `alt_cid` non-empty.

---

## Detector posture (agent / pull script — optional same chip or follow-up)

Prefer top-level `ok==false`. New verdicts:

1. Any `ingest_lease_dual` → dual-run  
2. Any `ingest_cache_id_fork` → fork  
3. `notify_complete_gate` with `code=notify_without_handoff` → dishonest complete  
4. `paper_notify_open` stage=`miss` → user-facing notify fail  
5. `papers_supersede_gc` where loser == in-flight handoff `cache_id` (join by cache_id + 2min window) → mid-handoff GC  

Script: extend `scripts/pull_evidence.py` filter flags (no UI).

---

## Floor / tests

| Item | Requirement |
|------|-------------|
| `evidence_kinds.py` + `evidence_kinds.dart` | add E1,E2,E4,E7 kinds |
| `evidence_floor.FROZEN_KINDS` + markers | emit sites listed |
| `tests/test_design_284_*.py` | kinds twin · safe_details prefix · markers present |
| Mobile test | `notify_complete_gate` details shape (unit) |

---

## Non-goals (explicit)

- Changing reclaim / lease claim algorithm  
- Blocking `showCompleted` on handoff fail (**product chip after this**)  
- Changing supersede GC policy  
- Main/SI pairing product fixes  
- Reducing `ingest_job_view_size` volume (noise; separate)

---

## Acceptance (agent-only)

After ship + one live dual-or-handoff incident, JSONL alone must answer:

1. Was there dual lease? (`ingest_lease_dual` or unequal tok on heartbeat densify)  
2. Who was supersede winner? (`details.winner_id` = `c…` present)  
3. Did we notify complete without handoff? (`notify_complete_gate ok=false`)  
4. Did user tap miss? (`paper_notify_open` miss)  
5. Can rows join on `job_id` **or** `content_hash` **or** `trace_id` for handoff↔supersede↔pump?

---

## Suggested implement order

1. P0a–c (winner_id + join keys) — unblocks reading old-style incidents  
2. E3 + E4 + E6 (handoff/notify bridge) — today’s dishonest success  
3. E1 + E2 (dual + fork) — root cause class  
4. E5 device pin + E7  

## Version

Pin: **0.3.279** (pubspec · config · Cloud Run). Incident device was **0.3.268**; densify requires APK+server ≥ this chip.
