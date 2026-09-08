# 186 — Device transfer pack (7-day opt-in cross-device)

Modules (planned):  
`transfer_pack_gcs.py` · `transfer_pack_ttl.py` · mobile pack import/export UI  
Parents: [185](185-local-paper-sot.md) · [184](184-ingest-artifact-ttl.md) · [144](144-paper-retention-ttl.md)

**Status:** LOCKED (not shipped; **after** 185 phases 1–5)  
**UI:** 설정/도서관 “다른 기기로 옮기기” · “이전 팩 받기” (클라우드에서 논문 **열람 UI 없음**)

---

## 0. Success / Fail

| Pass | Fail |
|------|------|
| 사용자가 로컬 논문 폴더(+선택: 노트/음성 등 번들 규칙)를 팩으로 업로드 | 상시 동기화 / 클라우드 도서관으로 오용 |
| 다른 기기 앱만 다운로드 → 로컬 `PaperDiskStore` import | 웹/관리자 UI에서 논문 본문 열람 |
| 업로드 완료 시각 + **7일** 후 팩 prefix 삭제 | `papers/` 또는 ingest_* 에 저장 |
| 소유자 uid만 pull | 타 uid / 만료 후 pull |
| 미리보기 = 제목·만료·크기만 | session 문장/그림 서버 렌더 |

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | **Opt-in only** — not continuous sync |
| J2 | Prefix: `users/{uid}/transfer_packs/{pack_id}/` — **never** under `papers/` or `ingest_*` |
| J3 | TTL clock starts at **upload complete**; default **168h**; kill `ASR_TRANSFER_PACK_TTL=0` disables create (existing packs still expire) |
| J4 | No cloud **viewer** for pack contents (product). List metadata only |
| J5 | Download → local import; optional delete-on-success; TTL is safety net |
| J6 | No merge of concurrent edits — import = replace folder or new `cache_id` (chip locks one) |
| J7 | Auth + size/count quotas; chunked upload/download (signed URLs preferred) |
| J8 | TTL module clones **184 patterns** (batch, dry-run, allowlist, evidence) — **not** 144 paper retention |
| J9 | Incomplete upload → shorter abandon TTL; active download lease prevents mid-pull purge |
| J10 | Depends on 185 `PaperDiskStore`; do not ship 186 before local SoT store exists |

---

## 2. Pack contents (v1 proposal)

Minimum (required): same as 185 paper folder (`session`, `figures`, layout, source, manifest).

Optional (product chip): include refs to notes/annotations/bookmarks/voice for that `cache_id` **inside the pack zip/tree** so the other device does not need cloud sync stores.  
If omitted, other device gets paper only; cloud sync stores may still exist under uid.

**Locked for v1 doc:** paper folder required; add-ons decided at implementation chip without breaking J1–J10.

---

## 3. Env

| Var | Default |
|-----|---------|
| `ASR_TRANSFER_PACK` | `0` until enable |
| `ASR_TRANSFER_PACK_TTL_HOURS` | `168` |
| `ASR_TRANSFER_PACK_ABANDON_HOURS` | `24` (incomplete) |
| `ASR_TRANSFER_PACK_MAX_BYTES` | chip |
| `ASR_TRANSFER_PACK_MAX_ACTIVE` | chip |
| `ASR_TRANSFER_PACK_TTL_DRY_RUN` | `0` |

---

## 4. Hazards

| # | Hazard | Mitigation |
|---|--------|------------|
| H1 | Namespace mix with papers/144/184 | Dedicated prefix + module |
| H2 | “Can't view” vs API still downloads | Owner-only; no preview body; short TTL |
| H3 | TTL during upload/download | Clock from complete; download lease |
| H4 | Huge packs / CR memory | Signed URL; size cap |
| H5 | Import overwrites wrong paper | Explicit replace UX; hash check |
| H6 | Orphan incomplete multipart | Abandon TTL + list GC |
| H7 | Evidence/ops 7d confusion | Separate kinds `transfer_pack_*` |

---

## 5. Phase

Ship only after 185: local store + handoff ACK + wipe path stable on mobile.
