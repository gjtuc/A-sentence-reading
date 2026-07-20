# 04 — API contract

Base: `http://127.0.0.1:8770`  
JSON only (multipart는 ingest만).

## 공통 에러 바디

```json
{
  "ok": false,
  "error": "error_code",
  "message": "human readable (ko or en)",
  "details": {}
}
```

`error` 코드 목록: [08-errors.md](08-errors.md)

## GET `/api/status`

```json
{
  "ok": true,
  "stage": "skeleton" | "m1" | "m2" | "m3" | "m4",
  "pdf_extract": false,
  "sentence_split": false,
  "version": "0.0.1"
}
```

마일스톤 완료 시 플래그를 true로 올린다.

## GET `/api/session/mock`

기존 유지. `session_id`는 `ses_mock` 고정 가능.

## POST `/api/ingest` (M1+ 목표 계약)

**Request:** `multipart/form-data`

| 필드 | 타입 | 필수 |
|------|------|------|
| `file` | PDF bytes | Y |

**Response 200:**

[01](01-data-model.md)의 `to_public_dict()` 전체 + `"ok": true`

**실패:**

| HTTP | error |
|------|-------|
| 400 | `invalid_pdf`, `not_pdf` |
| 413 | `file_too_large`, `payload_too_large` |
| 422 | `missing_file` |
| 501 | `not_implemented` (스켈레톤) |
| 504 | `extract_timeout` |
| 500 | `internal` |

## GET `/api/session/{session_id}`

메모리/디스크에 있는 세션 스냅샷. 없으면 404 `session_not_found`.

## PATCH `/api/session/{session_id}/cursor` (M4)

인덱스만 갱신 — 새로고침 없이 서버 진도 저장할 때.

```json
{ "figure_index": 2, "sentence_index": 40 }
```

**INVARIANT:** 한 요청에 둘 다 와도 되지만, 서버는 **각각 독립 clamp**만 한다. “문장 바꾸면 그림도” 같은 로직 금지.

Response: 갱신된 public dict.

## GET `/media/{session_id}/{figure_id}.png` (M3)

추출 PNG. Path traversal 금지 ([10](10-security-limits.md)).

## 프론트 호출 순서 (M4)

```
1. POST /api/ingest  → session_id
2. (선택) 로컬에 session_id 저장
3. render(public dict)
4. 네비는 클라이언트 로컬 state
5. (선택) debounce PATCH cursor
```

mock 모드: ingest 없이 `/api/session/mock`만.
