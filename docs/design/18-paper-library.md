# 18 — Paper library (보관 목록 UI)

모듈: `static/index.html` · `static/app.js` · `GET /api/cache/papers` · `POST …/open`

## 제품

- 헤더 **보관** → 로컬∪GCS index 목록
- 항목 클릭 → `/api/cache/papers/{id}/open` (로컬 miss 시 GCS pull)
- 파일 재업로드 없이 같은 `cache_id`로 탭 오픈 → 노트 키 `cache:{id}` 유지

## 불변조건

- 목록/열기는 AI 채점 없음
- 열 때만 sentence/figure 인덱스 로드 (사용자가 고른 논문)
- mock 탭은 실제 논문이 열리면 제거 (기존과 동일)

## 빈 목록

“보관된 논문이 없습니다…” — 파일 열기로 분석하면 쌓임.
