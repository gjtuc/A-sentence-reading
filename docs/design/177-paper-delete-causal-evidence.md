# 177 — Paper delete causal evidence densify

**Parent:** [169g](169g-causal-handoff-evidence.md) · [175](175-papers-gcs-orphan-invariant.md) · [102](102-cloud-library-delete.md)  
**Status:** DESIGN FROZEN → ship **0.3.160**  
**Trigger:** 2026-09-07 library delete showed `TimeoutException after 0:01:00` while evidence could not join client timeout ↔ server `paper_delete` ↔ residual ↔ concurrent translate.

**UI product change (honesty only):** on timeout/fail, **do not** drop the paper from the local list; show Korean timeout copy (not raw `TimeoutException`).

---

## 0. Locked judgments

| # | Judgment |
|---|----------|
| J1 | Delete debugging needs a **single handoff_id** from client start → server start → GCS wipe → client done. |
| J2 | Client **must** emit `client_api_timeout` with route `cache/delete` (today DELETE timeout was invisible as that kind). |
| J3 | Server **must** emit `paper_delete_start` **before** GCS work, with `elapsed_ms` on done. |
| J4 | If any in-memory ingest job still targets the same `cache_id`, emit `paper_delete_conflict` (counts only). |
| J5 | Residual wipe must emit **kind histogram** (`session`/`figure`/`layout`/`slot`/`source`/`other`) — no object path strings. |
| J6 | Local library list remove = **only after HTTP ok**. Timeout must leave the row visible. |
| J7 | Add-only floor; never shrink 169/175 sensors. |

---

## 1. New frozen kinds

```
paper_delete_start
paper_delete_done
paper_delete_conflict
papers_residual_kinds
```

Existing kept densified: `paper_delete` (server lifecycle), `papers_delete_residual`, `client_api_timeout`, `handoff`.

---

## 2. Client contract (mobile)

### 2.1 Sequence per id

```
handoff(client_delete → server_delete)  // existing
paper_delete_start {handoff_id, timeout_ms:60000}
HTTP DELETE + header X-Asr-Handoff-Id: {handoff_id}
  ok  → paper_delete_done stage=ok + paper_delete stage=ok; purge local; remove from list
  TimeoutException → client_api_timeout route=cache/delete
                      paper_delete_done stage=timeout elapsed_ms
                      KEEP list row; error = Korean soft message
  AsrApiException → paper_delete_done stage=http_fail http_status
  other → paper_delete_done stage=error
```

### 2.2 `deletePaper` API

- `.timeout(60s)` unchanged (product budget).
- On timeout: `_breadcrumbTimeout('cache/delete', e)` then rethrow.
- Optional `handoffId` → `X-Asr-Handoff-Id`.

### 2.3 Details allowlist (safe)

`handoff_id`, `elapsed_ms`, `timeout_ms`, `selected_n`, `ok_n`, `fail_n`, `stage` tokens via code field.

---

## 3. Server contract

### 3.1 `DELETE /api/cache/papers/{id}`

1. Read `X-Asr-Handoff-Id` (optional).
2. Emit `paper_delete_start` `{handoff_id?, cache_id}`.
3. Scan `_JOBS` for `target_cache_id|cache_id == id` and not discarded/done → `paper_delete_conflict` `{active_job_n, sample_stage}` (no job body).
4. `delete_cached_paper` (existing).
5. Emit densified `paper_delete` + handoff `client_delete→gcs_deleted` with **same** client handoff_id when present; `elapsed_ms`.
6. JSON body adds: `elapsed_ms`, `gcs_ok`, `residual_n`, `handoff_id` (echo).

### 3.2 Residual kinds

After prefix re-list, classify each residual name:

| class | heuristic |
|-------|-----------|
| session | ends with `session.json` |
| figure | `/figures/` or `.png` |
| layout | `layout_map` |
| slot | `slot_plan` |
| source | `source.pdf` / `source.docx` |
| other | else |

Emit `papers_residual_kinds` `{residual_n, n_session, n_figure, n_layout, n_slot, n_source, n_other}` whenever `residual_n>0` (in addition to `papers_delete_residual`).

---

## 4. Join recipe (agent)

```
mobile paper_delete_start.handoff_id
  == server paper_delete_start.handoff_id
  == server paper_delete.details.handoff_id
  == mobile paper_delete_done.handoff_id
+ client_api_timeout route=cache/delete in same trace window
+ optional paper_delete_conflict.active_job_n > 0
+ papers_residual_kinds if wipe incomplete
```

---

## 5. Tests

| # | Assert |
|---|--------|
| T1 | `classify_paper_blob_kind` table |
| T2 | Floor contains new kinds; py↔dart mirror |
| T3 | Dart: TimeoutException on delete keeps paper in list + soft error |
| T4 | Floor version pin 0.3.160 |

---

## 6. Out of scope

- Raising DELETE timeout above 60s (separate capacity chip)
- Cancelling live translate jobs on delete (detect only here; cancel = later)
- Changing GCS wipe algorithm beyond kind evidence

---

## 7. Ship

Bump app.py ×2 · pubspec · config → **0.3.160**. Deploy + APK.
