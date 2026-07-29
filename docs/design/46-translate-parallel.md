# 46 — 섹션 번역 문장 병렬 (동시 N)

모듈: `llm/translate_section.py`  
받침: [40](40-ingest-section-translate.md) · [43](43-translate-progress.md) · [45](45-progressive-translate.md)

## 무엇을

`enrich_session_translations` 안에서 **서로 독립인** Gemini 작업을  
`ThreadPoolExecutor` 로 동시에 돌린다. 품질 단계(draft→sense→polish→harmonize)는 그대로.

| 병렬 | 직렬 유지 |
|------|-----------|
| 같은 섹션 문장 pipeline | 섹션 digest (문장 EN 필요) |
| digest 후 문장 harmonize | digest 자체 |
| 캡션 pipeline들 | — |

## 동시성

- 기본 **4** (`ASR_TRANSLATE_WORKERS`, 클램프 1–8)
- status: `translate_workers` (실제 사용 상한)
- 콜백(`on_progress` / `on_item`)은 lock 으로 직렬화 — progressive UI·badge 깨지지 않게

진행 문구: 완료 개수 기준 (`초록 번역 5/12`) — 끝나는 순서는 비결정적.

## 비목표

- pipeline 1단화 (호출 수 줄이기)
- Live Enable / IPS — **Trading Gate. ASR 밖**
- Flutter
- Gemini 429 전용 재시도 정책 고도화 (기존 fail-soft 유지)

## 불변

- score/채점 없음
- TTS = 영어
- live 읽기 폴백 없음 (42)
- 보고 있는 문장 UI 고정 (45)

## 버전

0.2.54
