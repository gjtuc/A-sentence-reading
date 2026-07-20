# 01 — Data model (상세)

`models.py`의 계약. 구현 시 이 문서를 바꾸고 코드를 맞춘다.

## ID 규칙

| 엔티티 | `id` 형식 | 예 |
|--------|-----------|-----|
| Session | `ses_` + 22자 urlsafe | `ses_Ab3...` |
| Figure | `fig_{page:04d}_{ord:02d}` | `fig_0002_01` |
| Sentence | `sent_{ordinal:06d}` | `sent_000014` |

- ordinal은 **분할 결과 배열 순번** (원문 위치와 별개).
- 재ingest 시 같은 PDF라도 세션 ID는 새로 발급. 진행 복원은 `content_hash`로 ([05](05-session-store.md)).

## Figure

| 필드 | 타입 | 필수 | 의미 |
|------|------|------|------|
| `id` | str | Y | 위 규칙 |
| `image_src` | str | Y | UI용 URL (`/media/...`) 또는 data URL (mock만) |
| `storage_path` | str \| null | N | 서버 상대 경로. API 공개 dict에서는 숨김 가능 |
| `caption` | str | Y | 없으면 `""` |
| `page_index` | int \| null | N | 0-based |
| `width_px` | int \| null | N | |
| `height_px` | int \| null | N | |
| `byte_size` | int \| null | N | 필터용 |
| `kind` | `"embedded"` \| `"raster_fallback"` \| `"mock"` | Y | 추출 경로 추적 |

**INVARIANT:** `image_src`는 브라우저가 바로 로드 가능해야 한다. 로컬 절대경로는 넣지 않는다.

## Sentence

| 필드 | 타입 | 필수 | 의미 |
|------|------|------|------|
| `id` | str | Y | |
| `text` | str | Y | strip 후 비어 있으면 리스트에 넣지 않음 |
| `start_char` | int \| null | N | `raw_text` 기준 |
| `end_char` | int \| null | N | exclusive |
| `page_hint` | int \| null | N | 가능하면 추출 시 기입 (M2에서는 null 허용) |

**INVARIANT:** `text`에 앞뒤 공백 없음. 내부 개행은 공백 하나로 정규화(기본).

## PaperSession

| 필드 | 타입 | 의미 |
|------|------|------|
| `session_id` | str | |
| `title` | str | PDF 메타 또는 파일명 |
| `source_filename` | str | 원본 이름 |
| `content_hash` | str | SHA-256 hex of file bytes (진행 복원 키) |
| `figures` | list[Figure] | |
| `sentences` | list[Sentence] | |
| `figure_index` | int | |
| `sentence_index` | int | |
| `created_at` | ISO-8601 str | |
| `warnings` | list[str] | 추출 품질 경고 코드 ([08](08-errors.md)) |

### 인덱스 불변조건 (재확인)

```
advance_figure(±1)    → sentence_index unchanged
advance_sentence(±1)  → figure_index unchanged
empty figures         → figure_index == 0, current_figure() is None
empty sentences       → sentence_index == 0, current_sentence() is None
```

순환(wrap) 정책: **기본 ON** (마지막 → 처음). UX 문서와 동일. OFF로 바꾸려면 UX+이 문서를 함께 수정.

## `to_public_dict()` 최소 키

프론트가 의존하는 키 (이름을 바꾸지 말 것):

```json
{
  "session_id": "ses_...",
  "title": "...",
  "source_filename": "...",
  "figure_index": 0,
  "figure_count": 3,
  "sentence_index": 0,
  "sentence_count": 120,
  "figure": { "id", "image_src", "caption", "page_index" },
  "sentence": { "id", "text" },
  "figures": [ ... ],
  "sentences": [ ... ],
  "warnings": []
}
```

M1에서 `figures`/`sentences` 전체 배열을 내려준다 (논문 규모면 나중에 페이지네이션 — M5 이후).  
**1차 한도:** sentences ≤ 5000, figures ≤ 200. 초과 시 ingest 거부 (`payload_too_large`).
