# 21 — 진행 복원 (M5)

모듈: `static/progress.js` · `static/app.js` · ingest `content_hash` · mobile `progress_store` / `progress_gate`

## 무엇을

문장·그림 인덱스를 브라우저(및 앱 prefs)에 저장해, **새로고침·보관 재열기·같은 파일 재업로드** 후에도 읽던 위치로 돌아온다.

## 키

`localStorage` / prefs `asr.progress.v1` (+ uid 스코프 `.u.<uid>`):

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
- `/api/status` → `progress_restore: true` · `progress_fail_closed` (design/123)
- 킬스위치: `ASR_PROGRESS_FAIL_CLOSED=0` → 클라이언트 clamp 허용 (비상)

## UI

- `applySession` 시 mock 제외하고 저장된 인덱스 적용
- **design/123**: 저장된 값이 범위 밖/비정수면 **clamp 하지 않고 열기 거절** (에러 UI). 저장이 없으면 서버 기본(0)으로 연다.
- 복원 후 **점프만** (자동 TTS 없음)
- 문장/그림 이동 · 탭 전환 · 분기 리뷰에서 문장 선택 · `beforeunload` / `visibilitychange` / `pagehide` 시 저장
- 앱: 문장/그림 이동 + lifecycle paused/inactive/detached 시 prefs 저장

## 불변조건

- 그림/문장 인덱스 독립 — 진행 저장도 둘을 따로 둔다 (서로 덮어쓰지 않음).
- AI 채점 없음.
- 실패인데 성공 화면을 보이지 않는다 (fail-closed).

## 버전

0.3.37 (정밀·fail-closed · design/123). 이전 clamp 정책은 0.2.17~
