# 21 — 진행 복원 (M5)

모듈: `static/progress.js` · `static/app.js` · ingest `content_hash`

## 무엇을

문장·그림 인덱스를 브라우저에 저장해, **새로고침·보관 재열기·같은 파일 재업로드** 후에도 읽던 위치로 돌아온다.

## 키

`localStorage` `asr.progress.v1`:

```json
{
  "version": 1,
  "papers": {
    "cache:<id>": { "figure_index": 3, "sentence_index": 12, "at": "ISO" },
    "hash:<sha256>": { "figure_index": 3, "sentence_index": 12, "at": "ISO" },
    "ses:<session_id>": { "…" }
  }
}
```

조회·저장 우선순위: `cache:` → `hash:` → `ses:` / `id:`.  
저장 시 후보 키 **전부**에 같은 인덱스를 써서 cache↔hash 교차 복원이 된다.

## 서버

- 업로드·재분석: 원본 바이트 SHA-256 → 응답·보관 `content_hash`
- `/api/status` → `progress_restore: true`

## UI

- `applySession` 시 mock 제외하고 저장된 인덱스 적용 (clamp)
- 문장/그림 이동 · 탭 전환 · 분기 리뷰에서 문장 선택 · `beforeunload` 시 저장

## 불변조건

- 그림/문장 인덱스 독립 — 진행 저장도 둘을 따로 둔다 (서로 덮어쓰지 않음).
- AI 채점 없음.

## 버전

0.2.17
