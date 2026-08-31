# 166 — Reader annotations (mobile MVP)

**Version:** (구현 시 bump — 예: 0.3.100, 167과 동일 배치 가능)  
**Depends:** [63](63-mobile-reader.md) · [160](160-mobile-library-reader-polish.md) · [142](142-no-keyboard-sentence-notes.md) · [167](167-debone-quality-guards.md) (reanchor) · [163](163-figure-layout-edit-v2.md) (figure ink 분리)  
**Supersedes:** [141](141-mobile-sentence-notes.md) (**CANCELLED** — 키보드 노트 아님)

## 무엇인가

모바일 리더에서 **문장 하이라이트·밑줄·메모** (+ 이후 그림 프리핸드)를 남기고, **GCS sidecar**로 계정 간 동기화·export한다.

| 하지 않음 | 이유 |
|-----------|------|
| PDF embed 주석 | Chrome/Edge sync 깨짐 · re-debone 시 offset 소실 |
| 키보드 sentence notes (141) | design/142 취소 · 쉐도잉(녹음)은 유지 |
| LiquidText workspace / mind map | 2단계+ |
| 실시간 협업 | 3단계+ |
| AI 자동 하이라이트 편집 | 시스템 레이어 — 별도 (Moonlight 패턴) |

---

## Product (locked) — MVP (P0)

| 기능 | 스펙 |
|------|------|
| 하이라이트 | 4색: yellow, green, blue, pink |
| 밑줄 | P1 (스키마·UI 자리만 P0) |
| 메모 | 주석 이벤트 `note` 필드 (bottom sheet) |
| 범위 | **문장 전체** (P0); 부분 char range P1 |
| 제스처 | **문장 본문 long-press** → bottom sheet |
| 북마크 | 헤더 long-press 유지 (충돌 없음) |
| 그림 편집 | figure long-press → FigureEdit (163) 유지 |
| 로그인 | uid 없으면 SnackBar (북마크와 동일) |
| export | P1 — Markdown clipboard / `GET …/export` |
| 목록·점프 | P1 — Annotation list sheet (PDF Expert 패턴) |

### 레이어 분리 (locked)

| 레이어 | 저장 | UI |
|--------|------|-----|
| **시스템** | `session.json` — debone section, Body, `quality_flags`, (미래) auto-highlight | 섹션 헤더 · 품질 배너 ([167](167-debone-quality-guards.md)) |
| **사용자** | `users/{uid}/annotations/store_v1.json` | backgroundColor · note |
| **북마크** | `users/{uid}/bookmarks/store_v1.json` | nav header highlight |

동일 문장에 북마크 + 하이라이트 **공존** 가능.

---

## 벤치마크 (요약)

| 앱 | 가져올 것 |
|----|-----------|
| PDF Expert | Annotation summary · 색 필터 · export HTML/MD |
| DBpia | 하이라이트·밑줄·메모·색 필터·출처 복사 |
| MarginNote | 색 3~4개 + 1문장 메모 권장 |
| Hypothesis / W3C | TextQuoteSelector · sidecar |
| Polar / Apple Books | **반면교사** — lock-in · sync 버그 · export 없음 |

---

## GCS 객체

```
gs://{bucket}/{prefix}/users/{uid}/annotations/store_v1.json
```

`personal_object_name("annotations", "store_v1.json")` — [bookmarks_gcs.py](../../src/sentence_reading/llm/bookmarks_gcs.py) 패턴.

`ANNOTATIONS_STORE_MAX_BYTES = 2_000_000`

---

## Store 스키마 v1

```json
{
  "version": 1,
  "papers": {
    "cache:1dfd294ee1ee": {
      "sentences": {
        "experimental:5": [
          {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "at": "2026-08-31T05:44:12.345Z",
            "deleted": false,
            "kind": "highlight",
            "color": "yellow",
            "style": "solid",
            "motivation": "highlighting",
            "note": "촉매 활성도 핵심",
            "sentence_id": "sent_00015",
            "char_range": null,
            "selector": {
              "type": "TextQuoteSelector",
              "exact": "The catalytic activity",
              "prefix": "In this study, ",
              "suffix": " was measured at 800 °C."
            }
          }
        ]
      },
      "figures": {}
    }
  }
}
```

### 필드

| 필드 | 필수 | 설명 |
|------|------|------|
| `id` | ✅ | UUID v4 — merge 키 |
| `at` | ✅ | ISO8601 UTC |
| `deleted` | tombstone | `true` → compact 시 제거 |
| `kind` | ✅ | `highlight` \| `underline` \| `note` \| `ink` (figure) |
| `color` | highlight | `yellow` \| `green` \| `blue` \| `pink` |
| `style` | | `solid` \| `underline` \| `strikethrough` (EPUB Annotations 1.0) |
| `motivation` | | `highlighting` \| `commenting` \| `bookmarking` |
| `note` | | 메모 텍스트 |
| `sentence_id` | ✅ | debone id — reanchor 1차 |
| `char_range` | P1 | `[start, end)` plain offset; **null = 문장 전체** |
| `selector` | P1 | W3C TextQuoteSelector — reanchor 2차 |

### Map 키

- **문장:** `{sectionKey}:{position}` — `SectionNavIndex.sentenceBookmarkKeyForGlobal(i)`  
  예: `introduction:3`, `body:12`
- **그림 (P1):** `{kind}:{number}` — `FigureNavIndex.figureBookmarkKeyForCarousel(i)`  
  예: `figure:2`

**이유:** re-debone 후 `sentence_id`가 바뀌어도 section:position은 대부분 유지.

### Merge (서버 `annotations_gcs.py`)

- paper key별 merge
- sentence key별 **이벤트 배열** — `id`별 `at` 최신 wins
- `deleted=true` → compact 시 제거
- PUT = `merge(remote, local)` → upload → merged 반환 (bookmarks와 동일)

---

## API

### Sync

| Route | Method | Body / Response |
|-------|--------|-----------------|
| `/api/annotations/sync` | GET | `{ ok, available, store }` |
| `/api/annotations/sync` | PUT | `{ store }` → merged store |

계약은 [bookmarks sync](../../src/sentence_reading/api/app.py) (`/api/bookmarks/sync`) 와 동일:

- `needs_auth` / `available: false` → 로컬 유지 (fail-closed)
- auth: session cookie / bearer

### Export (P1)

```
GET /api/annotations/export?cache_id={id}&format=markdown|json
```

Markdown 예:

```markdown
## Experimental · 5
> The catalytic activity was measured at 800 °C.
📝 촉매 활성도 핵심
```

### Status

`/api/status` → `"annotations_sync": true`

---

## Server modules

| 파일 | 역할 |
|------|------|
| `llm/annotations_gcs.py` | **신규** — merge, upload, download |
| `api/app.py` | GET/PUT routes, status field |
| `tests/test_annotations_gcs.py` | **신규** |

`remove_paper_annotations(paper_key)` — design/102 패턴 (보관 삭제 시).

---

## Mobile modules

| 파일 | 역할 |
|------|------|
| `api/annotation_models.dart` | Store, PaperAnnotations, AnnotationEvent |
| `api/annotation_store.dart` | SharedPreferences `asr.annotations.v1.u.{uid}` |
| `api/annotation_gate.dart` | prune invalid bookmark keys |
| `state/annotation_controller.dart` | ChangeNotifier — BookmarkController 미러 |
| `widgets/annotation_toolbar_sheet.dart` | bottom sheet |
| `widgets/annotated_sentence_text.dart` | highlight render |
| `api/rich_sentence.dart` | `buildAnnotatedSpans` |
| `api/client.dart` | `fetchAnnotationsSync` / `pushAnnotationsSync` |

### `AnnotationController` (BookmarkController 대응)

| Bookmark | Annotation |
|----------|------------|
| `bindUid` / `clearSession` | 동일 |
| `loadPaper(cacheId)` | 동일 |
| `pullFromServer` / `pushToServer` / `schedulePush(500ms)` | 동일 |
| `applyNavPrune(sectionNav, figureNav)` | `annotation_gate.dart` |
| `toggleSentenceBookmark` | `upsertHighlight` / `removeAnnotations` |
| `purgePaper` | 동일 |

### Wiring

- `app.dart` — login: `bindUid`, `setServerAvailable(st.annotationsSync)`, `pullFromServer`
- `library_controller.dart` — open: `loadPaper` + `applyNavPrune` + `pullFromServer`
- `home_shell.dart` → `ReaderScreen(annotations: _annotations)`

---

## UI — 제스처 (locked)

| 영역 | 제스처 | 동작 |
|------|--------|------|
| Nav 헤더 (`ReaderNavHeaderLabel`) | long-press | 북마크 (기존) |
| 문장 Card 본문 (`_SwipePager` child) | **long-press** | 주석 bottom sheet |
| Figure Card | long-press | FigureEditScreen (163) |
| Figure (P1 ink) | double-tap | annotation mode toggle |

### Bottom sheet

```
┌──────────────────────────────────────┐
│ ─── drag handle                      │
│  🟡   🟢   🔵   🩷                    │
│  [ 메모 입력 (선택) ]                 │
│  [ 저장 ]  [ 삭제 ]                   │
└──────────────────────────────────────┘
```

색상:

```dart
yellow: Color(0xFFFFF59D)
green:  Color(0xFFC8E6C9)
blue:   Color(0xFFBBDEFB)
pink:   Color(0xFFF8BBD0)
```

opacity on text: `backgroundColor.withOpacity(0.4)`

### Flow `_handleSentenceAnnotateLongPress`

1. `annotations.canAnnotate`? else SnackBar
2. `key = nav.sentenceBookmarkKeyForGlobal(sentenceIndex)`
3. `existing = annotations.activeForSentenceKey(key)`
4. `showAnnotationToolbarSheet(...)`
5. save → `upsertHighlight(sentenceId, color, note, charRange: null)`
6. `HapticFeedback.mediumImpact()`

---

## Rendering — `buildAnnotatedSpans`

**문제:** `rich_sentence.dart`는 `<sub>`/`<sup>`/`<i>` 파싱. 하이라이트는 plain offset.

**알고리즘:**

1. Rich parse → segments with `(plainStart, plainEnd, text, style)`
2. `AnnotationRange` list merge per segment
3. P0: `char_range == null` → range `(0, plainLength)`

```dart
class AnnotationRange {
  final int start, end;
  final Color background;
  final bool underline;
}
```

`AnnotatedSentenceText` wraps `Text.rich(TextSpan(children: buildAnnotatedSpans(...)))`.

**P1:** `SelectableText.rich` + partial selection → `char_range` 저장.

---

## Annotation list (P1)

- AppBar `IconButton` + `Badge(count)`
- `showAnnotationListSheet` — section order, tap → `library.goToSentenceIndex(globalIdx)`
- 색 필터 chip: 전체 | 🟡 | 🟢 | 🔵 | 🩷

`SectionNavIndex.globalIndexForBookmarkKey(key)` — **신규 메서드**:

```dart
int? globalIndexForBookmarkKey(String bookmarkKey) {
  // parse sectionKey:pos → globalIndexFor(sectionIndex, pos-1)
}
```

---

## Figure ink (P1 — 본 문서 scope, 2차 구현)

| | Layout edit (163) | Figure annotation |
|--|-------------------|-------------------|
| 저장 | `figure_edit/commit` | annotations sidecar |
| 제스처 | long-press | double-tap ink mode |
| 좌표 | page bbox | normalized 0–1 (`figure_edit_geometry` 재사용) |

```json
"figures": {
  "figure:3": [{
    "id": "...",
    "kind": "ink",
    "paths": [{ "color": "#E53935", "width": 2.0, "points": [[0.1,0.2],[0.3,0.4]] }]
  }]
}
```

---

## Reanchor (depends 167 + reanalyze)

`POST /api/cache/papers/{id}/reanalyze` 후 문장 ID·텍스트 변경.

### 우선순위 (`annotation_reanchor.py` 또는 client)

1. `sentence_id` match + `texts_similar(old, new) ≥ 0.85` → keep
2. bookmark key still valid in new `SectionNavIndex` → update `sentence_id`, `status: reanchored_by_key`
3. `TextQuoteSelector` fuzzy match in new sentences → `reanchored_by_selector`
4. else → `status: orphaned` (목록에 ⚠, 사용자 삭제 선택)

클라이언트: `library_controller` open 후 `annotations.reanchorToSession(session)` → `schedulePush`.

Tombstone: 삭제 = `deleted: true` + new `at` (hard delete 금지).

---

## 테스트

### Python (`tests/test_annotations_gcs.py`)

- merge latest-at per `id`
- tombstone compact
- max bytes reject
- auth gate

### Dart

| ID | 케이스 |
|----|--------|
| D1 | `mergeAnnotationsStores` |
| D2 | `prunePaperAnnotations` invalid key |
| D3 | `buildAnnotatedSpans` whole-sentence yellow |
| D4 | `buildAnnotatedSpans` with `<sub>` + range |
| D5 | `AnnotationEvent` round-trip JSON |

### E2E (수동)

1. long-press → yellow → kill app → reopen → visible
2. device B login → pull → same
3. reanalyze → reanchor or orphaned

---

## 구현 체크리스트

### P0

- [ ] `llm/annotations_gcs.py`
- [ ] `api/app.py` — sync routes, status
- [ ] `annotation_models.dart` · `annotation_store.dart` · `annotation_gate.dart`
- [ ] `annotation_controller.dart`
- [ ] `client.dart` — sync methods
- [ ] `app.dart` · `library_controller.dart` wiring
- [ ] `annotation_toolbar_sheet.dart`
- [ ] `annotated_sentence_text.dart` · `rich_sentence.dart` extend
- [ ] `reader_screen.dart` — body long-press, render
- [ ] `tests/test_annotations_gcs.py` · dart unit tests

### P1

- [ ] `annotation_list_sheet.dart`
- [ ] `globalIndexForBookmarkKey`
- [ ] export API + share
- [ ] partial `char_range` + underline
- [ ] figure ink overlay
- [ ] `annotation_reanchor.py` + client reanchor

---

## 하지 않음

- 웹 주석 UI (웹은 legacy `notes/sync` v2 별도; 본 칩은 **모바일 MVP**)
- Obsidian/Readwise 자동 연동 (export만 제공)
- AI 요약 하이라이트 편집
- 141 키보드 노트 부활

---

## 참고 문서

- [16-sentence-notes.md](16-sentence-notes.md) — 웹 legacy
- [17-rumination-revisions.md](17-rumination-revisions.md) — append-only notes (웹)
- [142-no-keyboard-sentence-notes.md](142-no-keyboard-sentence-notes.md) — 모바일 키보드 노트 취소
