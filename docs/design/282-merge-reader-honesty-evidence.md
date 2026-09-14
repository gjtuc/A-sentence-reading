# 282 — Merge / reader honesty evidence (overkill)

Version: **0.3.277** · Status: **locked**  
Amends [279](279-mate-merge-pair-causal-evidence.md) · [169g](169g-causal-handoff-evidence.md) · [152](152-supplementary-merge.md) · [268](268-documents-mirror.md)

## Why

Live am2c04149 (2026-09-14, after 279):

1. User tapped **짝과 합치기**; library showed **메인+서플먼터리** · 문장 234 · 그림 35 (= 137+97 / 12+23).
2. Reader still Title/Table main-only; Documents mirror `session.json` stayed `supplementary_merged=false`, sent=137.
3. Agents inferred split-brain from UI+mirror — **no `paper_merge_*` postcheck, no reader honesty kind, no notify-open miss telemetry pulled**. 279 kinds exist but do not falsify “UI merged vs session main”.

Next chat must answer from JSONL alone: did local write succeed? did open load merged session? did notify miss fire? did mirror copy after handoff report ok?

## Hard constraints

- No title / path / filename / DOI / paper text / base64 / Korean tag strings in details
- Ids: `cache_id` / `main_id` / `si_id` opaque tokens only
- Allowlist **both** py + dart; add-only `FROZEN_KINDS` + emit markers
- **Observability only** — no merge/open product behavior change in this chip

## Locked emit map

### E1 — densify existing `reader_open` (stage=`ok` and local/hydrate stages)

Add details (ints / short tokens only):

| Field | Meaning |
|-------|---------|
| `supplementary_merged` | session flag 0/1 |
| `session_role` | normalized `main`\|`supplementary`\|`merged`\|`other` |
| `supp_section_n` | sentences with `section=supplementary` or id `si_*` |
| `entry_sent_n` / `entry_fig_n` | library row counts |
| `entry_role` | normalized entry doc_role |
| `tag_kind` | `merged`\|`pair`\|`si`\|`main`\|`other` (from role + can_merge; **not** raw libraryTag text) |
| `open_stage` | echo stage token |

### E2 — `reader_open_honesty` (every successful bind of `session=`)

Always record after open assigns a non-empty session:

| Field | Meaning |
|-------|---------|
| `mismatch_merged` | 1 if entry claims merged (`doc_role=merged` or tag_kind=merged) but session `supplementary_merged=0` |
| `mismatch_counts` | 1 if entry_sent_n>0 and ≠ session sentence_count |
| `mismatch_pair_open` | 1 if can_merge still true on entry while opening (pair not collapsed into merged session) |
| `supplementary_merged` | session |
| `sent_n` / `fig_n` / `supp_section_n` | session |
| `entry_sent_n` / `entry_fig_n` / `entry_role` / `tag_kind` | entry |
| `open_stage` | open path token |

Severity: `error` if any mismatch\*=1, else `lifecycle`.

### E3 — densify merge + `paper_merge_postcheck`

**`paper_merge_start`** add: `si_id_empty` 0/1, `entry_sent_n`, `entry_fig_n`, `entry_role`, `tag_kind`.

**`paper_merge_done`** keep path/counts; add `si_id_empty`.

**`paper_merge_postcheck`** — after merge attempt (local or server), **re-load** main `session.json` from PaperDiskStore:

| Field | Meaning |
|-------|---------|
| `merge_ok` | mergeSupplementary return 0/1 |
| `path` | `local`\|`server`\|`none` |
| `disk_hit` | session file loaded 0/1 |
| `disk_merged` | supplementary_merged on disk |
| `disk_sent_n` / `disk_fig_n` / `disk_supp_section_n` | from disk |
| `claimed_sent_n` / `claimed_fig_n` | counts used in merge_done (0 if unknown) |
| `mismatch_ui_disk` | 1 if merge_ok and (disk_merged=0 or claimed_sent_n>0 and claimed≠disk_sent) |

Severity: `error` if `mismatch_ui_disk=1` or (`merge_ok=1` and `disk_merged=0`).

### E4 — `paper_notify_open`

On `openByCacheId`: 

| Stage | When |
|-------|------|
| `hit` | entry found (before `open`) |
| `miss` | still missing after refresh |

Details: `id_len` only (not the id string if paranoid — actually cache_id field already allowed on bus). Use `cacheId=` as today. `after_refresh` 0/1 on miss path.

### E5 — `documents_mirror_done`

At existing `mirrorPaper` call sites (handoff; add emit wrapper):

| Field | Meaning |
|-------|---------|
| `ok` | mirror return |
| `trigger` | `handoff`\|`merge`\|`manual`\|… |
| `disk_merged` | SoT session supplementary_merged if readable else -1 |
| `disk_sent_n` | or -1 |

After **successful local merge only**, also call `mirrorPaper` then emit with `trigger=merge` (mirror already product for handoff; merge parity is observability of Documents vs SoT for agents — allowed as mirror sync, not merge logic change).

### E6 — floor

Freeze E2–E5 kinds + markers in `library_controller.dart` (+ `documents_mirror_store.dart` if emit lives there).

## Non-goals

- Fixing local merge append / server-vs-disk split (next chip, evidence-driven)
- Changing pairing 1+1 · auto-merge · soft-hide policy

## Tests

`tests/test_merge_reader_honesty_evidence_282.py` — design locked · kinds mirrored · markers · **0.3.277**

## Ship

**0.3.277**
