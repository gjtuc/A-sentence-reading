# 283 — Translate / ingest stage loop & regress evidence (overkill)

Version: **0.3.278** · Status: **locked**  
Amends [169g](169g-causal-handoff-evidence.md) · [169h](169h-translate-interior-checkpoints.md) · [168e](168e-ingest-stall-detector.md) · [158](158-ingest-auto-resume.md)

## Why

Live SI ingest (2026-09-14): UI showed **서론 재감수** climb toward N/135 then **restart from ~1/135**, user-observed **4th full repeat**.  

Existing sensors miss this:

| Sensor | Gap |
|--------|-----|
| `stall_fired` | Only when `percent\|message` **unchanged** ~300s — climbing then reset keeps changing |
| `checkpoint` `harmonize_pool_*` | Interior milestones; **no pass_n / regress first-class kind** |
| Auto-resume gate | Retries same stage on 504 but **no loop evidence** when job restarts section from 0 |

Agents cannot falsify “harmonize stuck in a loop” from JSONL alone.

## Hard constraints

- No paper text / titles / KO drafts / paths in details
- Section = snake token (`introduction`, `abstract`, …) via existing `_stage_token` / mobile map
- Phase = `translate` \| `digest` \| `harmonize` \| `caption` \| `other`
- Allowlist py + dart; add-only floor; **observability only** (no kill/resume policy change this chip)

## Locked emit map

### S1 — server (`translate_section.py` + tracker)

New kinds (also emit alongside existing `checkpoint` where useful):

| Kind | When | Details |
|------|------|---------|
| `translate_section_enter` | each `section_enter` | `section`, `pass_n` (1-based per job+section), `in_n`, `queue_i`, `queue_n` |
| `translate_harmonize_start` | harmonize pool start | `section`, `pass_n`, `in_n`, `worker_n` |
| `translate_harmonize_tick` | existing tick cadence | `section`, `pass_n`, `out_n`, `in_n`, `remaining` |
| `translate_harmonize_end` | pool end | `section`, `pass_n`, `out_n`, `in_n` |
| `translate_progress_regress` | `out_n` < last `out_n` for same job+section+phase | `section`, `phase`, `pass_n`, `prev_out_n`, `out_n`, `in_n` — severity **error** |
| `translate_stage_loop` | `pass_n >= 2` on section_enter or harmonize_start | `section`, `phase`, `pass_n` — severity **error** if pass_n≥3 else lifecycle |

Tracker lives in `src/sentence_reading/llm/translate_progress_guard.py` (per-process, keyed by `job_id|section|phase`).

### S2 — mobile (`LibraryController._noteIngestStageProgress`)

Parse upload badge `·` segment for `N/M` + phase keyword:

| Kind | When |
|------|------|
| `ingest_progress_regress` | same section+phase and `N` < previous `N` (or drop from ≥80% of M back to ≤20% of M) |
| `ingest_stage_loop` | same section+phase restarts (regress into low N) → increment `pass_n`; emit when pass_n≥2 |
| `ingest_stage_tick` | sampled: first tick, every 10th N, or N==M for current phase (lifecycle densify) |

Details: `section`, `phase`, `out_n`, `in_n`, `pass_n`, `percent` (ints / tokens only).

### S3 — auto-resume densify

On `_armAutoResumeAfterTimeout` when `should==true`: also emit `ingest_auto_resume_loop` with `pass_n=consecutive`, `stage_key_len`, `max`.

### S4 — floor

Freeze all new kinds + markers in `translate_section.py`, `translate_progress_guard.py`, `library_controller.dart`.

## Non-goals

- Changing stall seconds · stopping auto-resume · fixing why 재감수 restarts (next chip, evidence-driven)

## Tests

`tests/test_translate_stage_loop_evidence_283.py` — design · kinds · tracker unit (regress/loop) · markers · **0.3.278**

## Ship

**0.3.278**
