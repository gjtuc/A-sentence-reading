# 186 — Device transfer pack (7-day opt-in cross-device)

Modules:  
`transfer_pack_gcs.py` · `transfer_pack_ttl.py` · `app.py` · mobile `PaperDiskStore` export/import UI  
Parents: [185](185-local-paper-sot.md) · [184](184-ingest-artifact-ttl.md) · [144](144-paper-retention-ttl.md)

**Status:** SHIPPED (0.3.180)  
**UI:** 설정·계정 옆 「보관함 백업」 · 「백업된 보관함 논문 받기」 (전체 로컬 보관함 1팩; 클라우드 **열람 UI 없음**)

---

## 0. Success / Fail

| Pass | Fail |
|------|------|
| 로컬 논문 폴더를 팩으로 업로드 → 다른 기기 import | 상시 동기화 / 클라우드 도서관으로 오용 |
| 목록 = 제목·만료·크기만 | session/그림 서버 렌더·미리보기 |
| 업로드 **완료** 시각 + **168h** 후 prefix 삭제 | `papers/` 또는 `ingest_*`에 저장 |
| 소유자 uid만 pull | 타 uid / lease 중 purge |
| import = 같은 `cache_id` **교체** | 조용한 merge |

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | **Opt-in only** — not continuous sync |
| J2 | Prefix: `users/{uid}/transfer_packs/{pack_id}/` — **never** under `papers/` or `ingest_*` |
| J3 | TTL clock starts at **upload complete**; default **168h** |
| J4 | No cloud **viewer** for pack contents. List metadata only |
| J5 | Download → local `PaperDiskStore` import; optional delete-on-success; TTL is safety net |
| J6 | **Import = replace same `cache_id`** (no concurrent merge; no new id in v1) |
| J7 | Auth + quotas; **auth chunk/file API** in v1 (signed URL optional later) |
| J8 | TTL module clones **184 patterns** — **not** 144; never touch 184 allowlist |
| J9 | Incomplete → **24h** abandon; download **lease** blocks purge |
| J10 | Depends on 185 `PaperDiskStore` |
| J11 | Pack = paper folder (session, figures, layout, source, manifest) **plus** design/187 user artifacts when present: `user/bookmarks.json`, `user/annotations.json`, `shadowing/chunks.json`, `shadowing/takes.json`, `shadowing/voice/*.bin`. Full notes store still out of pack |
| J12 | `ASR_TRANSFER_PACK_MAX_BYTES` default **209715200** (200 MiB) |
| J13 | `ASR_TRANSFER_PACK_MAX_ACTIVE` default **3** ready+pending per uid |
| J14 | Upload/download piece size soft target **4 MiB** (client); server per-file cap = remaining quota |
| J15 | Kill `ASR_TRANSFER_PACK=0` → create/list/upload/download refuse; existing packs still TTL-purge if TTL enabled |

---

## 2. Layout

```text
users/{uid}/transfer_packs/{pack_id}/
  meta.json
  manifest.json
  files/session.json
  files/figures/{id}.png
  files/source.pdf|docx
  files/layout_map.json   # optional
  files/slot_plan.json    # optional
```

`meta.json`: `pack_id`, `cache_id`, `title`, `status` (`pending`|`ready`), `bytes`, `created_at`, `updated_at`, `complete_at`, `expires_at`, `download_lease_until`.

---

## 3. Env

| Var | Default |
|-----|---------|
| `ASR_TRANSFER_PACK` | `1` (0.3.180+) |
| `ASR_TRANSFER_PACK_TTL` | `1` (purge on even if pack API kill) |
| `ASR_TRANSFER_PACK_TTL_HOURS` | `168` |
| `ASR_TRANSFER_PACK_PIECE_MAX` | `4194304` |
| `ASR_TRANSFER_PACK_ABANDON_HOURS` | `24` |
| `ASR_TRANSFER_PACK_MAX_BYTES` | `209715200` |
| `ASR_TRANSFER_PACK_MAX_ACTIVE` | `3` |
| `ASR_TRANSFER_PACK_PURGE_INTERVAL_S` | `3600` |
| `ASR_TRANSFER_PACK_PURGE_BATCH` | `20` |
| `ASR_TRANSFER_PACK_TTL_DRY_RUN` | `0` |
| `ASR_TRANSFER_PACK_LEASE_SEC` | `1800` |

---

## 4. Hazards

| # | Hazard | Mitigation |
|---|--------|------------|
| H1 | Namespace mix with papers/144/184 | Dedicated prefix + module allowlist |
| H2 | “Can't view” vs API download | Owner-only; no preview body |
| H3 | TTL during upload/download | Clock from complete; download lease |
| H4 | Huge packs / CR memory | Per-file API; size/active caps |
| H5 | Import overwrites wrong paper | Explicit replace UX; sha verify |
| H6 | Orphan incomplete | Abandon TTL |
| H7 | Evidence/ops confusion | `transfer_pack_*` kinds only |
| H8 | Import calls `upload_paper_cache` | Forbidden — local SoT only |

---

## 5. Version

**0.3.180** · library bundle **0.3.186**
