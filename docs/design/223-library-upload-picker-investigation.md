# 223 — Library upload picker: implementation investigation (very careful)

Version: **investigation** · Product version pin when shipping: TBD (after 0.3.221)  
Depends: [70](70-mobile-upload.md) · [71](71-mobile-upload-resume.md) · [221](221-upload-reservation-queue.md) · [222](222-doc-role-detect-disk-honesty.md) · [218](218-supplementary-soft-pairing.md) · [185](185-paper-local-sot.md)

## Goal (user intent)

Custom / enriched upload UX:

1. Remember **where** a PDF was picked (display label / URI), **when** last uploaded
2. In picker, **green border** if that file’s bytes are **already in library**
3. Optional later: device PDF list, title + main/SI **preview** before upload
4. Must not break queue (221), resume (71), handoff (185), multi-user wipe

This doc is the **hazard-locked blueprint**. Do **not** ship the full picker in the same chip as SI detect (222).

---

## Current ground truth (0.3.220 → 0.3.221)

| Surface | Today |
|--------|--------|
| Pick | `FilePicker` + `withData: true` → bytes → `enqueuePickedPdfs` |
| Identity | SHA-256 (`content_hash`) |
| Queue | `asr.upload_reserve.v1` + `ingest_reserve/{hash}.pdf` |
| Active | singleton `asr.upload_draft.v1` + `ingest_drafts/` |
| Library list | `doc_role`, `library_tag`, **`content_hash` (added 222)** |
| Disk index | **`doc_role` + `contentHash` (added 222)** |
| Green join | **Possible after 222** via hash ∈ {remote list ∪ disk index} with `ingest_status` gate |

---

## Recommended chip sequence

### Chip A — Recent picks metadata only (MVP-safe)

**Ship**

- Prefs key **uid-scoped**: `asr.picker_recent.v1.u.$safeUid`
- On successful enqueue: append `{content_hash, display_name, label, uploaded_at_ms, source: saf|recent}`
- Cap N=30; drop oldest
- UI: thin “최근” section above system picker button; tap re-opens system picker or enqueues from reserve if bytes still present
- `clearAll` / logout **must** wipe this prefs key
- Evidence: reuse `upload_queue_*`; optional `picker_recent_save` with `n`/`hash8` only

**Do not ship in A**

- Green border, MediaStore, URI re-open, SI preview, path in evidence

### Chip B — Green “in library”

**INVARIANT**

- Join key = full `^[a-f0-9]{64}$` only
- Green = hash present in library SoT **and** user-visible success state
  - Prefer: `PaperEntry.contentHash` from list **or** disk index
  - Gate: not `failed` / not queue-only
- Distinct badges: `queued` / `uploading` / `in_library` / none

**EDGE**

- Same name different bytes → no green
- Main+SI both green → correct; copy = “이미 보관”, never “이미 연결”
- Missing hash on legacy rows → no green (fail-closed)
- Local-SoT after wipe → disk hash still greens

**FAIL-CLOSED**

- No filename/path/URI join
- Ambiguous → no green

**Prerequisite:** 222 list+disk hash/role (done)

### Chip C — Custom sheet (still SAF-backed)

- Bottom sheet: 최근 + 대기열 + “파일에서 추가” (system DocumentsUI)
- Multi-select still goes through `enqueuePickedPdfs` only
- Never parallel `uploadPdf`

### Chip D — MediaStore / device PDF scan (separate privacy review)

- Optional toggle; Play justification required
- Partial lists expected; never claim “전수”
- No upload of path lists to evidence/server

### Chip E — Title / main·SI preview (advisory only)

- On-device first-page text **or** light server probe
- Watermark: “추정 · 업로드 후 확정”
- Server `detect_doc_role` remains SoT
- Never gate enqueue on client role
- Never send client `doc_role` override by default

---

## Extremely careful hazards (must not regress)

### 1. Wrong green join
Filename / path / size / title join → wrong PDF marked done. **Hash only.**

### 2. SAF URI expiry
Persistable URI optional later; durable bytes = `ingest_reserve` / drafts. Re-upload must not depend on stale `content://`.

### 3. Multi-user leak
Global prefs for recent paths = A→B leak. **Uid-scoped + clearAll.**

### 4. Queue races
Picker must not call `uploadPdf` while pump runs. Cap 20. Don’t clear active draft when removing reserved item.

### 5. In-flight vs in-library
Queue/draft hash ≠ library green. Failed ingest ≠ green.

### 6. Pairing confusion
Green ≠ soft-pair ≠ merge. Two greens (main+SI) is normal.

### 7. Disk role lie (fixed in 222)
Never force `libraryTag: 메인` when `doc_role` known.

### 8. Client SI vs server
Preview wrong → user trust break; keep advisory.

### 9. RAM
Don’t keep all multi-select `Uint8List` after enqueue; prefer stream-to-reserve.

### 10. Evidence PII
No absolute paths / Korean folder names in `message` or details.

### 11. Same chip as SI detect
**Forbidden:** bundling MediaStore + green + SI detect + pairing algorithm changes together.

---

## Data model (Chip A+B sketch)

```text
PickerRecentItem:
  content_hash: hex64
  display_name: string   # PlatformFile.name only
  label: string          # optional folder hint, not full path
  uploaded_at_ms: int
  source: saf|recent|queue

LibraryHashSet:
  from PaperEntry.contentHash (list)
  ∪ PaperDiskIndexEntry.contentHash (bound uid)
  exclude ingest_status in {error} if exposed
```

---

## UI sketch (Chip C)

1. 보관 → PDF 가져오기 → sheet  
2. Section 최근 (green if in LibraryHashSet)  
3. Section 대기열 (queue badges)  
4. Button: 파일 앱에서 선택 → existing FilePicker multi  
5. Enqueue → existing pump / first_only auto-open  

---

## Test plan (when implementing)

- Hash rename: same bytes different name → green  
- Edit PDF: new hash → no green  
- Logout: recent empty  
- Enqueue while uploading: serial  
- Main+SI both green; merge still separate  
- Evidence: no path strings  

---

## Verdict

**가능.** 구현은 A→B→C 순. 222가 hash/role 디스크·API 정직성을 깔아 줌.  
전수 조사 + 제목/SI 미리보기는 **별도 고위험 칩**.
