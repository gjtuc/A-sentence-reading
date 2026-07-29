# 40 — 첨부 시 섹션 번역 + 요지 재감수 + 캡션

모듈: `llm/translate_section.py` · ingest hook · cache `text_ko`/`caption_ko`/`translate_digests`  
받침: [35](35-translate-simple.md) · [36](36-translate-pipeline.md) · [39](39-translate-side-by-side.md)

## 무엇을

논문 **첨부(ingest) 직후**에 섹션 단위로 번역을 미리 만든다.  
읽는 중 실시간 `/api/translate` 대기를 줄이고, **섹션 요지로 말투·용어를 한 번 더 맞춰** 기존 문장 파이프라인만보다 매끄럽게 만든다.

대상:

| 대상 | 필드 |
|------|------|
| 문장 | `text_ko` |
| 그림 캡션 | `caption_ko` |
| 섹션 요지(정리본) | `translate_digests[section].{en,ko}` |

## 파이프라인 (섹션마다)

1. 문장별 **기존** `draft → sense → polish` (`translate_dispatch` pipeline)
2. 섹션 영어 묶음 → **핵심 요지** (EN + KO 요약)
3. 요지를 가이드로 각 `text_ko` **재감수(harmonize)** — 말투·용어 통일
4. 해당 구간에 가까운 그림 캡션도 pipeline (+ 가능하면 같은 요지로 짧게 재감수)

Gemini 없으면 건너뛰고 경고만 (`translate_skipped`).

## 비목표 (이번)

- Flutter
- Live Enable / IPS (Trading Gate — ASR 밖)
- 실시간 스트리밍 번역 UI 제거 (캐시 miss 시 기존 live 폴백 유지)
- rich-v6 강제 재분석 (번역 전용 버전 `doc-v1` 별도)

## 저장

`session.json`:

```json
"translate_doc_version": "doc-v1",
"sentences": [{ "id", "text", "section", "text_ko": "..." }],
"figures": [{ ..., "caption_ko": "..." }],
"translate_digests": {
  "abstract": { "en": "...", "ko": "..." }
}
```

## UI

- 번역 on: 문장 `text_ko` 있으면 live API 생략 (EN|KO 좌우)
- 번역 on: 그림 캡션은 `caption_ko` 우선
- 섹션 경계 되새김질: **번역 정리본(digest)** 을 상단에 표시 + 문장별 KO 미리보기

## 불변

- INVARIANT: 읽기 인덱스 독립
- INVARIANT: 채점/점수 없음
- INVARIANT: TTS는 영문

## 버전

0.2.48
