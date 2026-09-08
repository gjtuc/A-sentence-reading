# 185 — Local paper SoT (device folder · cloud wipe after handoff)

Modules (planned):  
`mobile/lib/services/paper_disk_store.dart` · `library_controller.dart` ·  
`src/sentence_reading/llm/paper_handoff.py` · `papers_gcs.py` · `app.py`  
Parents: [18](18-paper-library.md) · [20](20-source-backup-reanalyze.md) · [121](121-library-open-gcs-first.md) · [144](144-paper-retention-ttl.md) · [171](171-device-figure-cache.md) · [175](175-papers-gcs-orphan-invariant.md) · [184](184-ingest-artifact-ttl.md)

**Status:** SHIPPED Phase 4 (0.3.179) + leftovers **0.3.181** (abandon TTL · bulk handoff · wipe polish)  
**UI:** 모바일 도서관/열기 경로 전환 (웹은 v1 범위 밖)  
**Target:** 별도 버전 칩 (0.3.178+ 단계적)

---

## 0. Success / Fail

| Pass | Fail |
|------|------|
| ingest ACK 후 폰에 완전한 논문 폴더 → 오프라인 열기·읽기·그림 OK | ACK 전 wipe로 논문 증발 |
| GCS `users/{uid}/papers/{cache_id}/` **객체 0** (해당 논문) | wipe 후 progressive/harmonize가 session 재업로드 |
| 클라우드에 도서관 **메타/index row 없음** (해당 논문) | ghost `index.json` + open 502 |
| 기기 분실 → **재업로드+재분석만** (복구 메타 없음) | “클라우드에 목록만” 반쪽 복구 |
| 분석·크롭·TTS/연습 파이프라인은 **서버만** | 클라이언트가 debone/layout 로직 복제 |
| evidence/ops는 클라우드 + 기존 TTL | papers wipe가 evidence/notes까지 삭제 |
| kill `ASR_PAPER_LOCAL_SOT=0` → 구 GCS SoT | 184 allowlist로 papers 삭제 |

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | **Device is SoT** for analyzed paper folder after successful handoff ACK |
| J2 | Cloud `papers/{cache_id}/` (session, figures, layout, **source**) deleted after ACK — no durable cloud copy |
| J3 | No cloud library meta for handed-off papers (`index.json` row removed; list SoT = device) |
| J4 | Device loss / new phone = **re-upload + re-analyze only** |
| J5 | Transfer of bytes = **simple chunk download** (manifest + checksums). No obfuscation theater |
| J6 | Protect server IP: layout/debone/figure-crop/TTS-practice **pipelines** stay on server; client only stores/assembles results |
| J7 | Handoff lifecycle: ingest durable → (optional finish KO/harmonize) → push chunks → **verify+ACK** → wipe. Never wipe before ACK |
| J8 | Post-ACK: all `upload_paper_cache` / `save_paper_session` GCS writes for that `cache_id` **refused** (late-writer resurrection ban) |
| J9 | Paper wipe **must not** call full `delete_cached_paper` user-store purge (notes/bookmarks/annotations/shadowing/voice stay unless user deletes paper on device) |
| J10 | design/184 stays **ingest_* only**; never delete `papers/` via ingest TTL |
| J11 | design/144 paper retention **off / N/A** for local-SoT papers (no 90d cloud expiry UX) |
| J12 | design/121 GCS-first open **does not apply** to handed-off papers; reader opens from `PaperDiskStore` |
| J13 | v1 scope = **mobile**; web library remains GCS-centric until a later chip |
| J14 | During analysis window only, short-lived GCS papers may exist (worker needs them) |
| J15 | Evidence kinds added (floor add-only): `paper_handoff_*`, `paper_cloud_wipe` — evidence bus stays cloud |

---

## 2. Artifact inventory

### 2.1 Paper folder (handoff payload → device)

```text
{cache_id}/
  session.json
  figures/{figure_id}.png
  layout_map.json          # if present
  slot_plan.json           # if present
  source.pdf|docx          # kept on device; wiped from cloud
  manifest.json            # handoff: paths, sizes, sha256, artifact_gen, content_hash
```

### 2.2 Stays on cloud (not part of paper wipe)

| Store | Prefix / module |
|-------|-----------------|
| Notes / bookmarks / annotations | `notes/` · `bookmarks/` · `annotations/` |
| Voice blobs | `voice/` |
| Shadowing chunks/takes | `shadowing/` (may be filled **before** wipe) |
| Evidence / ops | `evidence/` · ops JSONL |
| Ingest staging | `ingest_*` (184 TTL) |
| Transfer packs | `transfer_packs/` (**186**, separate) |

### 2.3 Device-only today → expand

| Today | 185 |
|-------|-----|
| Progress prefs | unchanged (device) |
| `FigureDiskCache` (171) | keep; prefer files from `PaperDiskStore/figures` |
| No durable session on disk | **add** `PaperDiskStore` |

---

## 3. Handoff protocol (normative)

1. Ingest reaches terminal success; `cache_id` known; papers objects uploaded (short-lived).
2. Server builds `manifest.json` (`artifact_gen`, `content_hash`, per-file `sha256`, `size`, `rel_path`).
3. Client pulls chunks (prefer **GCS signed URLs** during handoff window; fallback chunk API).
4. Client writes into `PaperDiskStore`, verifies every sha256.
5. Client `POST /api/cache/papers/{id}/handoff-ack` with `{content_hash, artifact_gen, file_count, ok:true}`.
6. Server verifies ack matches manifest generation → sets `handoff_acked` → **prefix delete** `papers/{id}/` + remove index row → emit `paper_cloud_wipe`.
7. Subsequent GCS paper writes for that id refused until new ingest creates a new generation.

**Partial failure:** no ACK → no wipe; client may retry pull; server may expire un-acked papers with a **short abandon TTL** (separate from 144; e.g. 48–72h) — lock in implementation chip.

---

## 4. Open / list / reanalyze (post-185)

| Action | Behavior |
|--------|----------|
| Library list | Mobile: local index only |
| Open / read / figures | Local session + local PNGs; no GCS pull |
| Reanalyze | Device uploads source (or triggers ingest with local source) → new handoff; clear progress + figure cache on `content_hash` change |
| Cloud `POST …/reanalyze` without source | `source_missing` is **expected** after wipe |
| User delete on device | Purge local folder + optionally sync-store keys; **no** cloud papers to delete |

---

## 5. Env / kills

| Var | Default | Meaning |
|-----|---------|---------|
| `ASR_PAPER_LOCAL_SOT` | `0` until cutover | `1` enable handoff+wipe path |
| `ASR_PAPER_HANDOFF_ABANDON_HOURS` | `72` | un-acked papers short TTL |
| `ASR_PAPER_OPEN_GCS_FIRST` | legacy | handed-off ids skip; kill still for pre-cutover |

---

## 6. Implementation hazards (locked)

| # | Hazard | Mitigation |
|---|--------|------------|
| H1 | 121 GCS-first open 502 after wipe | Local open path; skip refresh for acked ids |
| H2 | Library list empty / ghost index | Device index SoT; wipe removes index row |
| H3 | No mobile paper folder yet | Ship `PaperDiskStore` **before** wipe |
| H4 | Large payload / CR timeout (173) | Signed URL chunks; no base64 mega-/open |
| H5 | Late writers resurrect papers | Post-ACK upload refuse gate |
| H6 | Reanalyze needs cloud source | Device holds source; re-upload ingest |
| H7 | Figure hydrate GCS 404 | Local figures first |
| H8 | Multi-instance local disk re-upload | Gate on GCS/handoff flag, not local disk |
| H9 | Shadowing `load_cached_session` | Build before wipe or client sentence payload |
| H10 | `delete_cached_paper` strips notes | Wipe = papers prefix only |
| H11 | Progress fail-closed after reassemble | Clear/revalidate on hash change |
| H12 | 144 retention fights empty papers | Disable for local-SoT |
| H13 | 175 orphan audits scream | Empty papers after ACK = success |
| H14 | 184 confused with papers wipe | Separate module; never papers in 184 |
| H15 | Web still GCS-centric | v1 mobile only |
| H16 | Evidence locators stale | New handoff/wipe kinds; floor add-only |
| H17 | Wipe before ACK | Forbidden; abandon TTL only for stuck |
| H18 | Capacity: API streams tens of MB | Prefer signed URLs / worker |

---

## 7. Phase order (forced)

See § implementation plan in chat/canvas. Summary:

1. Lock docs (this + 186)  
2. Mobile `PaperDiskStore` + local list (**no wipe**)  
3. Handoff pull + verify + ACK API  
4. Invert open/hydrate to local  
5. Wipe + late-upload ban + 144 off  
6. Reanalyze = re-upload  
7. Shadowing / figure-edit independence  
8. Then [186](186-device-transfer-pack.md)

---

## 8. Relation to Coca-Cola analogy

- **Concentrate (secret):** server pipelines (exact crop, reading order, practice/TTS prep).  
- **Bottled product:** `session` + figures on device — **not** secret; no need to harden assembly.  
- Cloud after ACK: **no warehouse of bottles** — only factory + evidence + optional [186](186-device-transfer-pack.md) shipping crate.

---

## 9. Leftovers (0.3.181) — locked

| # | Judgment |
|---|----------|
| J19 | Abandon TTL only when handoff state `pending=True` ∧ `acked=False`, age from `manifest_built_at` (fallback `updated_at`) ≥ `ASR_PAPER_HANDOFF_ABANDON_HOURS` (default 72) |
| J20 | Abandon wipe = `delete_paper_cache_stats` only (papers prefix + index). **Never** `delete_cached_paper` (notes/bookmarks/shadowing stay) |
| J21 | Bulk handoff = client loops library rows lacking local session; reuse per-id handoff APIs; one-shot after refresh when `paper_handoff` |
| J22 | Shadowing `/build` sends `sentences` from open session or `PaperDiskStore` when cloud session gone |
| J23 | Figure hydrate arms from local disk session before `/open`; skip GCS arm when local figures suffice |
| J24 | Kill: `ASR_PAPER_HANDOFF_ABANDON_TTL=0` disables purge loop (default on). Dry-run: `ASR_PAPER_HANDOFF_ABANDON_TTL_DRY_RUN=1` |

Evidence (add-only): `paper_handoff_abandoned`, `paper_handoff_abandon_purge_tick`, `paper_bulk_handoff_start`, `paper_bulk_handoff_done`.
