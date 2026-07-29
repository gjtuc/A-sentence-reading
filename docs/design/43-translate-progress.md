# 43 — 섹션 번역 stage 진행 문구 세분화

모듈: `llm/translate_section.py` · `api/app.py` (ingest / cache backfill)  
받침: [40](40-ingest-section-translate.md) · [42](42-translate-ingest-only.md)

## 무엇을

`enrich_session_translations` 이 끝날 때까지 job badge 가
「섹션 번역·요지 정리 중」만 고정되던 것을, **단계별 메시지**로 바꾼다.

| 단계 | 예 메시지 |
|------|-----------|
| 문장 pipeline | `초록 번역 3/12` |
| 섹션 digest | `본문 요지 정리` |
| digest 재감수 | `본문 재감수 8/40` |
| 캡션 | `캡션 2/5` |

percent 는 translate 구간(대략 90–94 · 백필 88–93) 안에서 fraction 으로 올린다.

## 어떻게

- `on_progress(message: str, fraction: float)` 선택 콜백
- ingest / `_backfill_cached_translations` 이 `_job_set(..., stage="translate", message=...)` 로 연결
- 콜백 예외는 enrich 를 깨지 않음 (fail-soft)

## 비목표

- Gemini 호출 수 줄이기·병렬화 (속도 — 별도)
- UI 폴링 주기 변경
- Flutter · Live Enable / IPS

## 불변

- 번역 품질·결과 스키마(`text_ko` / digests) 동일
- score/채점 없음
- 버전 **0.2.51**
