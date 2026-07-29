# 42 — 읽기 중 실시간 번역 제거 · 보관본 번역 백필

모듈: `static/app.js` · ingest cache hit · `translate_section`  
받침: [40](40-ingest-section-translate.md)

## 무엇을

첨부(ingest) 때 만든 `text_ko` / `caption_ko` / `translate_digests` **만** 읽기 UI에 쓴다.

| 이전 (문제) | 이후 |
|-------------|------|
| 보관본에 KO 없어도 `/api/translate` live 폴백 | **live 폴백 없음** |
| rich-v6 보관본이면 번역 stage 스킵 | KO가 비면 **번역만 백필** 후 저장 |
| 구멍이 「번역 중…」으로 가려짐 | 「미리 번역 없음」으로 **드러냄** |

## UI

- 번역 on + `text_ko` 있음 → 즉시 표시 (API 호출 없음)
- 번역 on + `text_ko` 없음 → `미리 번역 없음 (파일을 다시 열거나 재분석)` (로딩 스피너 없음)
- 캡션: `caption_ko` 있을 때만 KO (기존과 동일, 데이터는 백필로 채움)

`POST /api/translate` 엔드포인트는 도구/계약용으로 **남기되**, 읽기 루프는 호출하지 않는다.

## 캐시 히트

`pipeline_version` 이 맞아 보관본을 써도:

1. 문장 `text_ko` 비율이 거의 0 이면 `needs_translate_backfill`
2. Gemini 있으면 `enrich_session_translations` → 같은 cache id 로 `save_paper_session`
3. 없으면 warning `translate_missing` / `translate_skipped_no_gemini`

## 비목표

- Flutter
- Live Enable / IPS (Trading Gate — ASR 밖)
- 이름-연도 인용 개선 (41 후속)
- `/api/translate` 엔드포인트 삭제

## 불변

- INVARIANT: 번역 on/off·백필은 `sentence_index` / `figure_index` 불변
- INVARIANT: TTS는 영문

## 버전

0.2.50
