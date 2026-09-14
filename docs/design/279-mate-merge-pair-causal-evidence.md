# 279 — Mate / merge / pairing causal evidence (overkill)

Version: **0.3.272** · Status: **locked**  
Amends [169g](169g-causal-handoff-evidence.md) · [152](152-supplementary-merge.md) · [261](261-cross-source-pair-set-row.md) · [275](275-import-green-set-evidence-honesty.md) · [278](278-soft-hide-undo-mate.md)

## Why

Live alumina (2026-09-14):

1. Soft-hide undo lost SI (278) — code had `paper_soft_hide` / `paper_soft_undo` emits, but **kinds were not on the client allowlist** → bus **silently dropped** them. Agents reconstructed from UI/disk, not JSONL.
2. Duplicate main after set re-enqueue → pairing skipped (1+1 rule) — **no pairing-pass evidence**.
3. User believed merge happened; session stayed `supplementary_merged=false`, fig_n=21 — **no merge start/done counts**. Failure-only `client_api_fail` is not enough.

Next chat must falsify: hide→undo mate expand, multi-main skip, local merge append counts — without guessing.

## Hard constraints

- No title / path / filename / DOI / paper text / base64 in details
- Ids: `cache_id` / `main_id` / `si_id` as existing short tokens only (already opaque hex prefixes OK)
- Allowlist **both** `evidence_kinds.py` + `evidence_kinds.dart`
- Add-only to `FROZEN_KINDS` + emit markers (169g)
- Observability only — **no** product merge/pairing behavior change in this chip

## Locked emit map

### E1 — allowlist existing soft-hide emits (bugfix for sensors)

Already recorded in `LibraryController`; were **not** allowlisted:

| Kind | Details (keep / densify) |
|------|---------------------------|
| `paper_soft_hide` | `n`, `requested_n`, `purge_at_ms` |
| `paper_soft_undo` | `n`, `requested_n` |
| `paper_soft_hide_abandon_work` | existing |
| `paper_soft_purge` | already allowlisted (275) |

### E2 — `library_pairing_pass` (mobile, every `_publishPapers`)

After soft-hide filter + `applyLocalPairingPass` (+ collapse counts):

| Field | Meaning |
|-------|---------|
| `papers_n` | after soft-hide filter |
| `hidden_n` | soft-hidden id count applied as filter |
| `keys_n` | distinct pairing keys considered |
| `paired_n` | rows with non-empty `pairedCacheId` after pass |
| `can_merge_n` | rows with `canMergeSupplementary` |
| `skip_multi_main_n` | keys with ≠1 main (blocks pair) |
| `skip_multi_si_n` | keys with ≠1 SI |
| `collapsed_n` | SI rows hidden by `collapsePairedSetRows` |
| `trigger` | short token: `publish` / `soft_hide` / `soft_undo` / `merge` / `refresh` / … |

### E3 — merge densify (mobile)

| Kind | When | Details |
|------|------|---------|
| `paper_merge_start` | enter `mergeSupplementary` | `main_id`, `si_id`, `can_merge` |
| `paper_merge_local_done` | end `_mergeSupplementaryLocal` | `ok`, `main_sent_n`, `si_sent_n`, `si_sent_kept_n`, `main_fig_n`, `si_fig_n`, `fig_bytes_ok_n`, `fig_bytes_miss_n`, `merged_sent_n`, `merged_fig_n` |
| `paper_merge_done` | after local or server path + before refresh | `ok`, `path`=`local`\|`server`, `merged_sent_n`, `merged_fig_n`, `supplementary_merged` |

On exception: keep `client_api_fail` `route=merge_supplementary`; still emit `paper_merge_done` `ok=0` when reachable.

### E4 — floor

Freeze all E1–E3 kinds + markers in `library_controller.dart` / `paper_disk_store.dart`.

## Non-goals

- Auto-merge · changing 1+1 pairing rule · Documents mirror · stripping soft-hide grace
- Fixing alumina merge on device (ops; separate)

## Tests

`tests/test_mate_merge_pair_evidence_279.py` — design locked · kinds mirrored · markers · version **0.3.272**

## Ship

**0.3.272**
