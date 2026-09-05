# 175 — Papers GCS orphan invariant (index ≠ prefix)

Modules: `llm/papers_gcs.py` (`merge_index_entries`, `upload_paper_cache`, `delete_paper_cache_stats`) · `cache/paper_cache.py` (`save_paper_session`, `delete_cached_paper`) · evidence kinds (add-only floor)  
받침: [17](17-rumination-revisions.md) · [108](108-fail-closed-no-cache.md) · [121](121-library-open-gcs-first.md) · [174](174-worker-gcs-uid-library-list.md)

## Symptom (live evidence, 2026-09-05)

Owner `116191504131668885631` under `gs://asr-chaheon-warehouse/asr/users/{uid}/papers/`:

| Layer | Count |
|-------|------:|
| `index.json` entries | **1** (`79cb4af49327`, Sep 5 upload) |
| GCS `papers/{cache_id}/` prefixes | **48** |
| Orphans (prefix ∉ index) | **47** |
| Bytes | ~183 MB total · ~7 MB keep |

Orphan **classes** (recursive object list):

| Class | n | Meaning |
|-------|--:|---------|
| `layout_slot_only` | 33 | `layout_map.json` + `slot_plan.json` only |
| `full_or_partial_content` | 9 | still has `session.json` (+ often source/figures) |
| `body_without_session` | 5 | figures / layout left, no session |

Same-title full orphans (prove supersede):

- `de1d782e1c7a` · `5294653df2cb` · `e7cda4a1e209` — *In situ and operando…* (Sep 1)
- keep `79cb4af49327` — same title (Sep 5)

**App library is not lying** — index is the product list. GCS prefixes are the durable store. Divergence = invariant break, not “user forgot to delete.”

Silently `gsutil rm` the 47 folders would **hide** the bug and destroy forensic signal. Do not treat purge-as-fix.

---

## Root causes (ordered)

### RC1 — Title supersede drops index id without GC (primary for *full* orphans)

`merge_index_entries` keeps **one** row per `(title_key, source, doc_role)` — newer `updated_at` wins; older **different** `cache_id` is removed from the merged index and never passed to `delete_paper_cache`.

`save_paper_session` also strips local same-title rows before insert, then `upload_paper_cache` merges remote ∪ local → remote losers disappear from `index.json` while `papers/{old_id}/**` stay forever.

This is intentional UX (“one library card per title”) with a **missing GC side effect**.

### RC2 — Delete is session-meta walk, not prefix wipe (primary for *layout_slot_only* / *body_without_session*)

`delete_paper_cache_stats`:

1. download `session.json` → delete session  
2. delete only `figures[]` paths named in that session  
3. delete `source.pdf|docx`  
4. rewrite index without id  

**Never deletes** `layout_map.json` / `slot_plan.json`.  
**Never** `list`+delete unknown blobs under `papers/{id}/`.  

So every successful user delete that once had layout artifacts leaves a two-object tomb; partial figure lists leave `body_without_session`.

### RC3 — Index read-modify-write without generation CAS (amplifier)

`download_remote_index` → merge → `upload_bytes` has **no** `ifGenerationMatch`. Concurrent API/worker/patch uploads can lose entries (or resurrect stale sets). Amplifies RC1 and can create full orphans without an explicit delete.

### RC4 — Upload writes objects before index confirm (secondary)

`upload_paper_cache` order: session → figures → layout → source → **then** index.  
`index_upload_fail` after object writes leaves a prefix not listed. design/174 closes the ingest “success without list” hole when uid is bound; it does not compensate already-written objects on index failure, and does not GC supersede losers.

### Non-cause for *these* user-prefix orphans

design/174 (worker uid empty → `personal_object_name` None) prevents writes to `users/{uid}/papers/`. It explains “done but not in library,” not “folders under this uid with no index row” from successful-uid uploads + supersede/delete gaps.

---

## Product invariants (locked)

1. **Library truth** = personal `papers/index.json` entries.  
2. **Store truth** = objects under `papers/{cache_id}/`.  
3. **Invariant I175**: every `cache_id` with any object under the prefix **must** be in the index *or* explicitly marked `tombstone/orphan` with evidence — never silent leftover.  
4. **Supersede** (same title_key, new id wins) **must** GC the loser prefix (or enqueue durable GC) in the same success path that rewrites the index.  
5. **Delete success** = prefix empty (or only documented tombstone) **and** id absent from index. Layout/slot/figures not in session meta still count.  
6. Ops may purge orphans only after evidence classification + user/ops ack — not as the “fix.”

---

## Solution plan (phased)

### Phase A — Detect (no data loss)

- Script / Cloud Run admin: `list papers/*` vs `index.entries` → classify like live table above.  
- Evidence (add-only floor): `papers_gcs_orphan_sample` / `papers_index_ghost` (id in index, no session).  
- Status or ops report: `papers_orphan_n`, `papers_orphan_bytes` (counts only).

### Phase B — Delete completeness (fixes RC2)

- `delete_paper_cache_stats`: after meta walk, **prefix list-delete** all objects under `papers/{cid}/` (incl. layout/slot/stray figures).  
- Emit `paper_delete_gcs` with `object_n` / `residual_n`; `ok` only if residual 0 (or retry once).  
- Tests: upload layout+session → delete → prefix empty.

### Phase C — Supersede GC (fixes RC1)

- When `merge_index_entries` (or `save_paper_session`) drops ids by title_key, collect **loser ids**.  
- Call the same prefix-delete path; emit `papers_supersede_gc` `{winner, losers[], ok}`.  
- Fail-closed option (ingest): if loser GC fails, still list winner but set `orphan_gc_pending` + evidence (do not pretend store is clean).

### Phase D — Index CAS (fixes RC3)

- `upload_remote_index`: read generation → write with `if_generation_match` → on conflict re-download, re-merge, retry (bounded).  
- Tests for concurrent merge retaining both distinct titles and GC losers.

### Phase E — Upload compensation (RC4)

- On `index_upload_fail` after object writes: retry index; if still fail, emit `papers_upload_fail` and **either** roll back prefix **or** leave marked orphan for Phase A (product choice: prefer rollback for new uploads).  
- Keep design/174 ensure-listed for ingest terminal.

### Phase F — Reconcile existing 47 (after A–C land)

- One-shot reconcile job: classify → GC `layout_slot_only` / `body_without_session` / superseded full clones of current title → **retain** any full orphan the user still wants (explicit allow-list).  
- Never “delete all not in index” without classification report.

**Done 2026-09-05 (uid `116191504131668885631`)** — after live `0.3.157`:

| | pre | post |
|--|----:|-----:|
| index_n | 1 | 1 (`79cb4af49327`) |
| prefix_n | 48 | 1 |
| orphan_n | 47 | **0** |
| GC | — | 47/47 ok (layout 33 · full 9 · body 5) |

Allow-list = index only. Forensic: `.tmp_orphan_audit_pre.json` · `.tmp_orphan_reconcile_plan.json` · `.tmp_orphan_audit_post.json` (local; not product code).

---

## Kill / rollback

- Feature flags: `ASR_PAPERS_PREFIX_DELETE=0`, `ASR_PAPERS_SUPERSEDE_GC=0`, `ASR_PAPERS_INDEX_CAS=0`.  
- Detection-only (Phase A) always safe.

## Version

**0.3.157** — dense defaults ON (`ASR_PAPERS_PREFIX_DELETE` · `ASR_PAPERS_SUPERSEDE_GC` · `ASR_PAPERS_INDEX_CAS`).

Shipped in code: prefix wipe delete, supersede GC on upload merge, index CAS helper, audit script `scripts/audit_papers_gcs_orphans.py`, evidence `papers_supersede_gc` / `papers_delete_residual` / `papers_gcs_orphan_sample`.

Existing 47 orphans: reconcile only after deploy + audit report (Phase F) — not silent rm.
